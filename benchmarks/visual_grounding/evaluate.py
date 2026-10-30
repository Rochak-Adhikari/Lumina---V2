"""P3.2-V offline scorer and P3.1 fake-proposal replay. No execution adapter.

Ground truth is private to scoring and the explicitly labelled oracle fake.
The provider-facing payload has only the screenshot, goal and observation ref.
Bounding boxes/evidence are benchmark sidecars, not new production action fields.
"""
import asyncio
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import time
import tracemalloc

from lumina.computer_action import ObservationRef, SafeError
from lumina.computer_use_model import (
    parse, ProviderIdentity, ImageConsent, ModelPolicy, build_request,
    ComputerUseModel, FakeImageTransport)
from lumina.control_authority import ControlAuthority
from lumina.observations import ObservationStream

ACTIONS = frozenset({'click', 'ask'})
INTERACTIVE = frozenset({'button', 'textfield', 'menuitem', 'icon', 'toggle'})
OPAQUE = INTERACTIVE | {'background', 'window', 'panel', 'canvas', 'card'}
IDENTITY = ProviderIdentity('fake', 'ground-truth-oracle', 'visual-corpus-v1')


def reference(case):
    opaque = hashlib.sha256(case['id'].encode()).hexdigest()[:24]
    return ObservationRef('synthetic-session', 'screen-' + opaque, 1)


def wire(case, action):
    return json.dumps({'version': 1, 'observation': asdict(reference(case)),
                       'action': action}, allow_nan=False).encode()


def box_iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union > 0 else 0.


def contains(box, point):
    return box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]


def visible_hit(case, point):
    # Same back-to-front paint order as render(). Coarse occluded metadata is
    # insufficient for partially covered controls: inspect the actual point.
    for obj in reversed(case['objects']):
        if obj['type'] in OPAQUE and contains(obj['bbox'], point):
            return obj if obj['type'] in INTERACTIVE and obj['enabled'] else None
    return None


def sidecar_valid(value):
    if type(value) is not dict or set(value) != {'bbox', 'target_type', 'evidence'}:
        return False
    if (type(value['evidence']) is not str or not 0 < len(value['evidence']) <= 1024
            or type(value['target_type']) is not str or len(value['target_type']) > 80):
        return False
    box = value['bbox']
    return box is None or (type(box) is list and len(box) == 4
        and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in box)
        and box[0] < box[2] and box[1] < box[3])


def score(case, raw, grounding):
    """No execution; invalid outputs remain in denominators and never earn a hit."""
    proposal = parse(raw, ACTIONS, reference(case))
    valid = not isinstance(proposal, SafeError)
    result = {'case_id': case['id'], 'family': case['family'], 'split': case['split'],
              'size': case['size'], 'expected_abstain': case['expected_abstain'],
              'structured_valid': valid, 'sidecar_valid': sidecar_valid(grounding),
              'target_identified': False, 'action_correct': False, 'abstained': False,
              'proposal_correct': False, 'target_type_correct': False,
              'hallucinated_or_unsupported': not valid, 'decoy_hit': False,
              'bbox_iou': None, 'localization_error_px': None,
              'localization_error_diagonal': None, 'evidence_token_support': None}
    if not valid:
        return result
    action = proposal.action
    result['abstained'] = action.kind == 'ask'
    result['action_correct'] = action.kind == case['expected_action']['kind']
    if action.kind == 'ask':
        result['proposal_correct'] = case['expected_abstain']
        return result
    w, h = case['size']
    point = (action.point[0]*w, action.point[1]*h)
    hit = visible_hit(case, point)
    hits = [hit] if hit is not None else []
    result['hallucinated_or_unsupported'] = not hits or case['expected_abstain']
    target = case['target']
    if target is None:
        return result
    result['target_identified'] = (contains(target['bbox'], point)
                                   and any(o['id'] == target['id'] for o in hits))
    result['proposal_correct'] = (result['target_identified'] and result['action_correct']
        and action.button == case['expected_action'].get('button')
        and action.count == case['expected_action'].get('count'))
    result['decoy_hit'] = bool(hits) and not result['target_identified']
    center = ((target['bbox'][0]+target['bbox'][2])/2,
              (target['bbox'][1]+target['bbox'][3])/2)
    distance = math.dist(point, center)
    result['localization_error_px'] = distance
    result['localization_error_diagonal'] = distance / math.hypot(w, h)
    if result['sidecar_valid']:
        result['target_type_correct'] = grounding['target_type'] == target['type']
        box = grounding['bbox']
        # Missing box counts as 0 on actionable cases; do not drop failures.
        result['bbox_iou'] = box_iou([box[0]*w, box[1]*h, box[2]*w, box[3]*h],
                                    target['bbox']) if box else 0.
        tokens = target['evidence_tokens']
        result['evidence_token_support'] = all(
            token.casefold() in grounding['evidence'].casefold() for token in tokens)
    return result


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator/denominator if denominator else None}


def aggregate(rows):
    """All-case denominators. Missing/invalid boxes earn zero, not exclusion."""
    n = len(rows)
    actionable = [r for r in rows if not r['expected_abstain']]
    ambiguous = [r for r in rows if r['expected_abstain']]
    errors = [r['localization_error_px'] for r in actionable
              if r['localization_error_px'] is not None]
    scaled = [r['localization_error_diagonal'] for r in actionable
              if r['localization_error_diagonal'] is not None]
    return {
        'cases': n,
        'target_identification_accuracy': ratio(sum(r['target_identified'] for r in actionable), len(actionable)),
        'mean_bbox_iou_all_actionable': (sum(r['bbox_iou'] or 0 for r in actionable)/len(actionable) if actionable else None),
        'localization_error_px_mean': statistics.mean(errors) if errors else None,
        'localization_error_diagonal_mean': statistics.mean(scaled) if scaled else None,
        'localization_measured': len(errors),
        'localization_missing': len(actionable)-len(errors),
        'action_type_accuracy': ratio(sum(r['action_correct'] for r in rows), n),
        'proposal_accuracy': ratio(sum(r['proposal_correct'] for r in rows), n),
        'target_type_accuracy': ratio(sum(r['target_type_correct'] for r in actionable), len(actionable)),
        'structured_output_validity': ratio(sum(r['structured_valid'] for r in rows), n),
        'sidecar_validity': ratio(sum(r['sidecar_valid'] for r in rows), n),
        'unsupported_or_hallucination_rate': ratio(sum(r['hallucinated_or_unsupported'] for r in rows), n),
        'appropriate_abstention_rate': ratio(sum(r['abstained'] for r in ambiguous), len(ambiguous)),
        'unnecessary_abstention_rate': ratio(sum(r['abstained'] for r in actionable), len(actionable)),
        'decoy_error_rate': ratio(sum(r['decoy_hit'] for r in actionable), len(actionable)),
    }


def grouped(rows, key):
    values = sorted(set(str(r[key]) for r in rows))
    return {value: aggregate([r for r in rows if str(r[key]) == value]) for value in values}


def oracle_sidecar(case):
    target = case['target']
    if target is None:
        return {'bbox': None, 'target_type': '', 'evidence': 'Ambiguous or unavailable target; ask the user.'}
    w, h = case['size']
    b = target['bbox']
    return {'bbox': [b[0]/w, b[1]/h, b[2]/w, b[3]/h],
            'target_type': target['type'], 'evidence': ' / '.join(target['evidence_tokens'])}


def request_context(case, image):
    # Synthetic fixed clock; no production config, Runtime or desktop source.
    clock = lambda: 100.
    stream = ObservationStream(clock=clock)
    ref = reference(case)
    stream.start(ref.session_id)
    obs = stream.publish(image, session_id=ref.session_id, source_id=ref.source_id,
        source_type='browser', sequence=ref.sequence, captured_at=None,
        received_at='synthetic', received_monotonic=clock(),
        capture_not_before_monotonic=clock(), timing_basis='browser_ticket',
        original_dimensions=tuple(case['size']), processed_dimensions=tuple(case['size']), desktop=None)
    authority = ControlAuthority(clock=clock)
    assert authority.resume()
    consent = ImageConsent('benchmark-owner', stream, ref.session_id, ref.source_id,
                           'synthetic-window', IDENTITY, clock()+20)
    policy = ModelPolicy(consent, actions=ACTIONS)
    request = build_request(case['goal'], obs, (), policy, 2)
    return stream, authority, request


async def replay_fake(case, image, raw=None):
    """Oracle fake checks plumbing only; GT never reaches a real model."""
    reply = wire(case, case['expected_action']) if raw is None else raw
    stream, authority, request = request_context(case, image)
    transport = FakeImageTransport(IDENTITY, (reply,))
    proposer = ComputerUseModel(transport, authority, owner='benchmark-owner')
    start = time.perf_counter()
    try:
        result = await proposer.propose(request)
        proposal = proposer.take(result)
        return {'status': result.status, 'proposal': proposal,
                'fake_requests': transport.calls,
                'latency_ms': (time.perf_counter()-start)*1000,
                'operations_admitted': len(authority.reconciliation_inventory())}
    finally:
        await proposer.close()
        stream.stop()


async def run_fake_benchmark(output):
    from .corpus import write_corpus
    import PIL
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    started, cpu = time.perf_counter(), time.process_time()
    tracemalloc.start()
    try:
        manifest = write_corpus(output/'corpus')
        rows, traces, latencies = [], [], []
        for case in manifest['cases']:
            image = (output/'corpus'/case['fixture']).read_bytes()
            raw = wire(case, case['expected_action'])
            sidecar = oracle_sidecar(case)
            replay = await replay_fake(case, image, raw)
            assert replay['status'] == 'proposal' and replay['operations_admitted'] == 0
            rows.append(score(case, raw, sidecar))
            latencies.append(replay['latency_ms'])
            traces.append({'case_id': case['id'], 'status': replay['status'],
                           'untrusted_proposal': asdict(replay['proposal']),
                           'sidecar_from_ground_truth': sidecar,
                           'fake_requests': replay['fake_requests'],
                           'operations_admitted': replay['operations_admitted'],
                           'latency_ms': replay['latency_ms']})
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    result = {
        'tier': 'DETERMINISTIC_ORACLE_FAKE_ONLY_NOT_MODEL_PERFORMANCE',
        'provider': asdict(IDENTITY), 'actual_model_inference_count': 0,
        'actual_inference_cost_usd': 0, 'fake_request_count': len(traces),
        'actual_model_qualification': 'NOT_PERFORMED_ACCESS_AND_TRANSPORT_UNQUALIFIED',
        'aggregate': aggregate(rows), 'by_family': grouped(rows, 'family'),
        'by_size': grouped(rows, 'size'), 'by_split': grouped(rows, 'split'),
        'resource_scope': 'Fixture generation and fake replay only; tracemalloc excludes native Pillow buffers and process RSS.',
        'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu,
        'python_traced_peak_bytes': peak, 'pillow_version': PIL.__version__,
        'fake_latency_ms_p50': statistics.median(latencies),
        'fake_latency_ms_p95': sorted(latencies)[math.ceil(.95*len(latencies))-1],
        'metric_limits': [
            'Identity is a hit on the labelled visible target region, not semantic comprehension.',
            'Box/evidence sidecars are benchmark-only; P3.1 has no such output fields.',
            'Evidence token matching is not proof of a truthful visual explanation.',
            'Center distance is reported with missing counts; all-actionable IoU includes failures as zero.',
            'Holdout is family-disjoint preparation, not a blind or unseen model evaluation.',
            'Expected postconditions are annotations only; no action is executed or verified on Windows.'],
        'rows': rows, 'traces': traces}
    with (output/'fake-results.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Offline oracle fixture replay; no actual model or execution.')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = asyncio.run(run_fake_benchmark(args.output))
    print(json.dumps({k: result[k] for k in ('tier', 'actual_model_inference_count', 'fake_request_count')}))

