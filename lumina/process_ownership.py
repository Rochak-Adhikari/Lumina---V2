"""M12: Retained Process Ownership and Verified Cleanup Settlement.

Implements an immutable, lifetime-bound process ownership abstraction for an
explicitly created disposable application process instance and its child-process lifetime.
Integrates with M11 ControlAuthority and TaskManager contracts without bypassing them.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import inspect
import secrets
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from .control_authority import (
    ControlAuthority,
    OwnedWorker,
    SimulatedWorkerCleanupAdapter,
    WorkerCleanupGrant,
    WorkerCleanupReceipt,
)


class ProcessState(str, Enum):
    """Observable states of a retained process handle."""
    STILL_ACTIVE = 'still_active'
    EXITED = 'exited'
    ACCESS_DENIED = 'access_denied'
    INVALID_HANDLE = 'invalid_handle'
    UNVERIFIABLE = 'unverifiable'


class ChildLifetimeGuarantee(str, Enum):
    """Guarantees about descendant process lifetimes relative to the root process."""
    NO_GUARANTEE = 'no_guarantee'                  # Untracked descendants may outlive root process
    TRACKED_CHILD_HANDLES = 'tracked_child_handles' # Explicit list of retained handles for all known children
    JOB_OBJECT_BOUND = 'job_object_bound'          # Kernel Job Object bounds all descendants (future native)


class SettlementOutcome(str, Enum):
    """Independently verified exit settlement outcomes."""
    CONFIRMED_QUIESCENT = 'confirmed_quiescent'   # Root process and all tracked children confirmed exited
    ROOT_STILL_ACTIVE = 'root_still_active'       # Root process has not exited
    CHILDREN_STILL_ACTIVE = 'children_still_active' # Root exited, but one or more children remain active
    CHILDREN_UNVERIFIABLE = 'children_unverifiable' # Root exited, but children cannot be verified
    INACCESSIBLE = 'inaccessible'                 # Root or child handle cannot be queried
    TIMEOUT = 'timeout'                           # Settlement verification timed out
    UNKNOWN = 'unknown'                           # Other uncertainty or error


def reject_pid_only_operation(pid: Any) -> None:
    """Enforce Safety Property 1: A PID alone is never sufficient authorization."""
    raise PermissionError(
        f"A PID alone ({pid!r}) is never sufficient authorization for process lifecycle operations. "
        "Retained handle ownership, creation timestamp, and admitted authority grant are required."
    )


class RetainedProcessHandle:
    """Retained process handle abstraction.
    
    Holds an owned handle to a specific OS process instance.
    The handle keeps the OS process kernel object alive even after process exit,
    preventing PID reuse ambiguity when querying exit status and exit codes.
    """
    def __init__(self, pid: int, create_time: float, handle_id: Optional[str] = None):
        self.pid = int(pid)
        self.create_time = float(create_time)
        self.handle_id = handle_id or secrets.token_hex(8)
        self._is_closed = False

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def query_state(self) -> Tuple[ProcessState, Optional[int]]:
        """Query the process state and exit code using the retained handle."""
        raise NotImplementedError

    def wait(self, timeout: float = 0.0) -> bool:
        """Wait up to timeout seconds for process exit. Returns True if exited."""
        raise NotImplementedError

    def request_termination(self, exit_code: int = 1) -> bool:
        """Request termination of the process instance. Returns True if dispatched."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the retained handle, releasing the kernel object reference."""
        self._is_closed = True


class FakeProcessHandle(RetainedProcessHandle):
    """Deterministic fake process handle for offline testing.
    
    Never calls OS APIs. Controllable via state setters and events.
    """
    def __init__(self, pid: int, create_time: float, *,
                 initial_state: ProcessState = ProcessState.STILL_ACTIVE,
                 initial_exit_code: Optional[int] = None,
                 handle_id: Optional[str] = None):
        super().__init__(pid, create_time, handle_id)
        self._state = initial_state
        self._exit_code = initial_exit_code if initial_state == ProcessState.EXITED else None
        self.terminate_called_count = 0
        self.fail_termination = False
        self.inaccessible_on_query = False
        self.invalid_on_query = False
        self.exit_event: Optional[asyncio.Event] = None

    def query_state(self) -> Tuple[ProcessState, Optional[int]]:
        if self._is_closed or self.invalid_on_query:
            return ProcessState.INVALID_HANDLE, None
        if self.inaccessible_on_query:
            return ProcessState.ACCESS_DENIED, None
        return self._state, self._exit_code

    def set_exited(self, exit_code: int = 0) -> None:
        self._state = ProcessState.EXITED
        self._exit_code = exit_code
        if self.exit_event is not None and not self.exit_event.is_set():
            self.exit_event.set()

    def request_termination(self, exit_code: int = 1) -> bool:
        if self._is_closed:
            raise ValueError("Cannot terminate using a closed handle.")
        self.terminate_called_count += 1
        if self.fail_termination:
            return False
        if self.exit_event is None:
            self._state = ProcessState.EXITED
            self._exit_code = exit_code
        return True

    def wait(self, timeout: float = 0.0) -> bool:
        if self._is_closed or self.invalid_on_query or self.inaccessible_on_query:
            return False
        return self._state == ProcessState.EXITED


class OwnedProcessInstance:
    """Immutable resource identity for an explicitly created disposable process.
    
    Tied to the exact process instance via instance_id, pid, create_time, and root_handle.
    Stores creating owner, worker generation, task, child lifetime guarantee, and tracked children.
    """
    def __init__(
        self,
        *,
        instance_id: Optional[str] = None,
        pid: int,
        create_time: float,
        task_id: str,
        owner: str,
        worker_generation: str,
        root_handle: RetainedProcessHandle,
        child_guarantee: ChildLifetimeGuarantee = ChildLifetimeGuarantee.NO_GUARANTEE,
        tracked_children: Sequence[RetainedProcessHandle] = (),
        created_at: Optional[float] = None,
    ):
        self.instance_id = instance_id or f"proc-{secrets.token_hex(12)}"
        self.pid = int(pid)
        self.create_time = float(create_time)
        self.task_id = str(task_id)
        self.owner = str(owner)
        self.worker_generation = str(worker_generation)
        self._original_root_handle = root_handle
        self.root_handle = root_handle
        self.child_guarantee = child_guarantee
        self.tracked_children = tuple(tracked_children)
        self.created_at = created_at if created_at is not None else time.monotonic()
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed or self.root_handle.is_closed

    def validate_scope(self, owner: str, task_id: str, generation: str) -> None:
        """Validate that caller's scope matches this exact process instance."""
        if owner != self.owner:
            raise PermissionError(f"Owner mismatch: expected {self.owner}, got {owner}")
        if task_id != self.task_id:
            raise PermissionError(f"Task mismatch: expected {self.task_id}, got {task_id}")
        if generation != self.worker_generation:
            raise PermissionError(f"Generation mismatch: expected {self.worker_generation}, got {generation}")

    def matches_exact_instance(self, pid: int, create_time: float, handle: Optional[RetainedProcessHandle] = None) -> bool:
        """Verify exact process instance; rejects PID reuse with different timestamp or handle."""
        if self.pid != pid:
            return False
        if abs(self.create_time - create_time) > 1e-6:
            return False
        if handle is not None and handle is not self._original_root_handle:
            return False
        return True

    def independent_settlement_check(self) -> Tuple[SettlementOutcome, Dict[str, Any]]:
        """Independently verify exit settlement via retained handles.
        
        Does not trust termination dispatch return values alone.
        Explicitly distinguishes confirmed exit, running, inaccessible, and partial child states.
        """
        # Safety Property: If root handle was mutated or replaced, refuse verification
        if self.root_handle is not self._original_root_handle or not self.matches_exact_instance(self.root_handle.pid, self.root_handle.create_time, self._original_root_handle):
            return SettlementOutcome.INACCESSIBLE, {'reason': 'replacement_handle_detected', 'pid': self.pid}

        if self.root_handle.is_closed:
            return SettlementOutcome.INACCESSIBLE, {'reason': 'root_handle_closed', 'pid': self.pid}

        root_state, root_code = self.root_handle.query_state()
        if root_state == ProcessState.STILL_ACTIVE:
            return SettlementOutcome.ROOT_STILL_ACTIVE, {'pid': self.pid, 'state': root_state.value}
        if root_state in (ProcessState.ACCESS_DENIED, ProcessState.INVALID_HANDLE, ProcessState.UNVERIFIABLE):
            return SettlementOutcome.INACCESSIBLE, {'pid': self.pid, 'state': root_state.value}
        if root_state != ProcessState.EXITED:
            return SettlementOutcome.UNKNOWN, {'pid': self.pid, 'state': root_state.value}

        # Root process is confirmed EXITED.
        # Check tracked children first: if ANY child is still active or unverifiable,
        # neither TRACKED_CHILD_HANDLES nor a mere JOB_OBJECT_BOUND label can claim quiescence!
        if self.tracked_children:
            for child in self.tracked_children:
                if child.is_closed:
                    return SettlementOutcome.CHILDREN_UNVERIFIABLE, {
                        'child_pid': child.pid,
                        'reason': 'child_handle_closed',
                    }
                c_state, c_code = child.query_state()
                if c_state == ProcessState.STILL_ACTIVE:
                    return SettlementOutcome.CHILDREN_STILL_ACTIVE, {
                        'child_pid': child.pid,
                        'state': c_state.value,
                    }
                if c_state in (ProcessState.ACCESS_DENIED, ProcessState.INVALID_HANDLE, ProcessState.UNVERIFIABLE):
                    return SettlementOutcome.CHILDREN_UNVERIFIABLE, {
                        'child_pid': child.pid,
                        'state': c_state.value,
                    }
                if c_state != ProcessState.EXITED:
                    return SettlementOutcome.UNKNOWN, {
                        'child_pid': child.pid,
                        'state': c_state.value,
                    }

        # If NO_GUARANTEE, root exit alone does not prove untracked descendants exited.
        if self.child_guarantee == ChildLifetimeGuarantee.NO_GUARANTEE:
            return SettlementOutcome.CHILDREN_UNVERIFIABLE, {
                'pid': self.pid,
                'root_exit_code': root_code,
                'reason': 'no_child_lifetime_guarantee',
            }

        # When all tracked children are confirmed exited under TRACKED_CHILD_HANDLES or verified JOB_OBJECT_BOUND:
        return SettlementOutcome.CONFIRMED_QUIESCENT, {
            'root_exit_code': root_code,
            'children_count': len(self.tracked_children),
            'guarantee': self.child_guarantee.value,
        }

    def request_tree_termination(self, exit_code: int = 1) -> Dict[str, bool]:
        """Dispatch termination request to root and all tracked child handles.
        
        Refuses to terminate a replacement handle not matching original creation identity.
        """
        dispatches = {}
        # If root_handle was replaced, refuse to terminate the replacement under original authorization!
        if self.root_handle is self._original_root_handle and self.matches_exact_instance(self.root_handle.pid, self.root_handle.create_time, self._original_root_handle):
            dispatches['root'] = self._original_root_handle.request_termination(exit_code)
        else:
            dispatches['root'] = False

        for idx, child in enumerate(self.tracked_children):
            dispatches[f"child_{idx}_{child.pid}"] = child.request_termination(exit_code)
        return dispatches

    def close_all_handles(self) -> None:
        """Close root and child retained handles upon confirmed removal."""
        self._original_root_handle.close()
        if self.root_handle is not self._original_root_handle:
            # Do not close foreign replacement handle
            pass
        for child in self.tracked_children:
            child.close()
        self._closed = True


class DisposableProcessCleanupAdapter(SimulatedWorkerCleanupAdapter):
    """Adapter coordinating disposable process cleanup with M11 ControlAuthority.
    
    Enforces exact grant admission, synchronous termination effect boundary,
    and independent settlement verification using retained handles.
    """
    persistent = True

    def __init__(self, instance: OwnedProcessInstance, *, settlement_timeout: float = 5.0):
        self.instance = instance
        self.settlement_timeout = settlement_timeout
        self.effects: List[str] = []
        self.entered = asyncio.Event()
        self.before_effect = asyncio.Event()
        self.before_effect.set()
        self.release = asyncio.Event()
        self.release.set()
        self.fault: Optional[str] = None
        self.settlement_history: List[Tuple[SettlementOutcome, Dict[str, Any]]] = []

    async def _wait_for_settlement(self) -> Tuple[SettlementOutcome, Dict[str, Any]]:
        """Wait/poll up to settlement_timeout for process settlement."""
        start = time.monotonic()
        while True:
            outcome, details = self.instance.independent_settlement_check()
            if outcome == SettlementOutcome.CONFIRMED_QUIESCENT:
                return outcome, details
            if outcome not in (SettlementOutcome.ROOT_STILL_ACTIVE, SettlementOutcome.CHILDREN_STILL_ACTIVE):
                return outcome, details
            elapsed = time.monotonic() - start
            if elapsed >= self.settlement_timeout:
                return outcome, details
            await asyncio.sleep(min(0.01, max(0.001, self.settlement_timeout - elapsed)))

    async def cleanup(self, authority: ControlAuthority, grant: WorkerCleanupGrant) -> WorkerCleanupReceipt:
        self.entered.set()
        await self.before_effect.wait()

        # Step 1: Exact grant scope and resource instance validation
        if grant.binding.resource is not self.instance:
            raise PermissionError("Grant binding resource is not this OwnedProcessInstance")
        self.instance.validate_scope(grant.binding.owner, grant.binding.task_id, grant.binding.generation)

        # Step 2: Fault injection before effect
        if self.fault == 'exception_before_effect':
            raise RuntimeError('synthetic exception before effect')
        if self.fault == 'cancelled_before_effect':
            raise asyncio.CancelledError()

        # Step 3: Synchronous fake effect dispatched through authority under Stop lock
        def effect():
            self.effects.append(grant.operation)
            if grant.operation == 'cancel':
                self.instance.request_tree_termination()
            elif grant.operation == 'remove':
                outcome, _ = self.instance.independent_settlement_check()
                if outcome != SettlementOutcome.CONFIRMED_QUIESCENT:
                    raise PermissionError('Cannot remove unsettled process resource')
                self.instance.close_all_handles()

        authority.worker_cleanup_effect(grant, self.instance, effect)

        await self.release.wait()

        # Step 4: Fault injection after effect
        if self.fault == 'exception':
            raise RuntimeError('synthetic exception after effect')
        if self.fault == 'cancelled':
            raise asyncio.CancelledError()
        if self.fault == 'ack':
            return None  # Acknowledgement-only without valid receipt

        # Step 5: Independent settlement verification
        if grant.operation == 'remove':
            return WorkerCleanupReceipt(
                attempt=grant.token,
                ownership=grant.binding.token,
                worker_generation=grant.binding.generation,
                operation='remove',
                quiescent=True,
                removed=True,
            )

        # For cancellation: independently verify process and child exit settlement
        outcome, details = await self._wait_for_settlement()
        self.settlement_history.append((outcome, details))

        quiescent = (outcome == SettlementOutcome.CONFIRMED_QUIESCENT)

        receipt = WorkerCleanupReceipt(
            attempt=grant.token,
            ownership=grant.binding.token,
            worker_generation=grant.binding.generation,
            operation='cancel',
            quiescent=quiescent,
            removed=False,
        )

        if self.fault == 'generation':
            return WorkerCleanupReceipt(
                attempt=grant.token,
                ownership=grant.binding.token,
                worker_generation='mismatched_generation',
                operation='cancel',
                quiescent=quiescent,
                removed=False,
            )
        if self.fault == 'partial':
            return WorkerCleanupReceipt(
                attempt=grant.token,
                ownership=grant.binding.token,
                worker_generation=grant.binding.generation,
                operation='cancel',
                quiescent=False,
                removed=False,
            )

        return receipt
