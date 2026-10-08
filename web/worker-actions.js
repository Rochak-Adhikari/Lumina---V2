// Trusted UI confirmation, bound server-side to one task/action for 60 seconds.
export async function workerAction(post,action,task){
  const request=await post('/api/tasks',{action:`request_${action}`,task_id:task.task_id});
  const consequence=action==='cancel'?'Stop this agent and terminate its terminal session? Unsaved work may be lost.':'Remove this inactive agent from the panel? Its files and logs will be kept.';
  if(!window.confirm(`${consequence}\n\n${request.worker} · ${request.task_id}\n${request.instruction.slice(0,160)}`))return null;
  const result=await post('/api/tasks',{action,task_id:task.task_id,confirmation_id:request.confirmation_id});
  if(result.status==='CANCEL_FAILED')throw Error(result.summary||'The agent did not confirm cancellation.');
  return result;
}
