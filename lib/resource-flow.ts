export const externalMaterialLinkProps = {
  target: "_blank",
  rel: "noopener noreferrer",
} as const;

export function completionAccuracy(attempted: number, correct: number) {
  return attempted > 0 ? Math.round((correct / attempted) * 100) : 0;
}

export function taskStageKey(taskId: number, stage: string) {
  return `${taskId}:${stage}`;
}

export type ResourceFilters = {
  subject:string;
  provider:string;
  type:string;
  difficulty:string;
  access:string;
  scope:string;
  topic:string;
  showUnavailable:boolean;
};

function searchable(values: unknown[]) {
  return values.filter(value=>value!==null&&value!==undefined).join(" ").toLowerCase();
}

export function filterResourceOptions(options:TaskResourceOption[], query:string, filters:ResourceFilters) {
  const needle=query.trim().toLowerCase();
  return options.filter(option=>{
    if(!filters.showUnavailable&&!option.available)return false;
    if(filters.subject&&option.subject!==filters.subject)return false;
    if(filters.provider&&option.provider!==filters.provider)return false;
    if(filters.type&&option.type!==filters.type)return false;
    if(filters.difficulty&&option.difficulty!==filters.difficulty)return false;
    if(filters.access==="FREE"&&!option.free)return false;
    if(filters.access==="PAID"&&!option.requires_subscription)return false;
    if(filters.scope==="CORE"&&!option.cat_core)return false;
    if(filters.scope==="OPTIONAL"&&option.cat_core)return false;
    if(filters.topic&&!searchable([option.topic_slug,option.category,option.title,option.tags]).includes(filters.topic.toLowerCase()))return false;
    return !needle||searchable([
      option.title,option.provider,option.provider_title,option.test_reference,option.topic_slug,
      option.category,option.platform_path,option.tags,option.description,option.subject,option.type,
    ]).includes(needle);
  });
}

export function searchCalendarTasks(tasks:StudyTask[], query:string) {
  const needle=query.trim().toLowerCase();
  if(!needle)return [];
  return tasks.filter(task=>searchable([
    task.title,task.topic,task.subject,task.kind,task.detail,task.resource,
    task.time_foundation_test?.test_reference,task.time_foundation_test?.provider_title,
    ...task.resource_stages.flatMap(stage=>[
      stage.provider,stage.provider_title,stage.title,stage.description,stage.platform_path,
      stage.resource_type,stage.test_reference,stage.category,stage.tags,stage.topic_slug,
    ]),
  ]).includes(needle)).sort((a,b)=>a.date.localeCompare(b.date)||a.start_time.localeCompare(b.start_time));
}
import type { StudyTask, TaskResourceOption } from "./types";
