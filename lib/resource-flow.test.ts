import { describe, expect, it } from "vitest";

import type { AppData, StudyTask, TaskResourceOption } from "./types";
import { applyTaskMovePatch, completionAccuracy, externalMaterialLinkProps, filterResourceOptions, isTaskMovePatch, searchCalendarTasks, taskStageKey, type ResourceFilters } from "./resource-flow";

describe("study material return flow", () => {
  it("opens external material without replacing the plan tab", () => {
    expect(externalMaterialLinkProps).toEqual({
      target: "_blank",
      rel: "noopener noreferrer",
    });
  });

  it("calculates recorded accuracy and stage option keys", () => {
    expect(completionAccuracy(20, 16)).toBe(80);
    expect(completionAccuracy(0, 0)).toBe(0);
    expect(taskStageKey(42, "PRACTICE")).toBe("42:PRACTICE");
  });
});

const baseFilters:ResourceFilters={subject:"",provider:"",type:"",difficulty:"",access:"",scope:"",topic:"",showUnavailable:false};
const resource=(value:Partial<TaskResourceOption>):TaskResourceOption=>({id:"resource",provider:"RODHA",provider_title:"Rodha",title:"Quadratic Equations",description:"Concept lesson",subject:"QA",topic_slug:"quadratic-equations",url:"https://example.com",platform_path:null,type:"CONCEPT",free:1,requires_subscription:0,difficulty:"FOUNDATION",available:1,test_reference:null,category:"Algebra",tags:"quadratic algebra",cat_priority:"HIGH",cat_core:1,subscription_name:"",exact_topic_match:true,subject_match:true,planner_score:1,recommended:true,current:false,...value});

describe("full resource catalogue filtering",()=>{
  const options=[resource({}),resource({id:"time-test",provider:"TIME",provider_title:"T.I.M.E.",title:"Foundation - Quadratic Equations - 1",test_reference:"OBQ1001812",free:0,requires_subscription:1,available:0})];
  it("searches titles and provider test references",()=>{
    expect(filterResourceOptions(options,"quadratic",baseFilters)).toHaveLength(1);
    expect(filterResourceOptions(options,"OBQ1001812",{...baseFilters,showUnavailable:true})[0].id).toBe("time-test");
  });
  it("hides unavailable paid providers until explicitly requested",()=>{
    expect(filterResourceOptions(options,"",baseFilters).map(item=>item.id)).toEqual(["resource"]);
    expect(filterResourceOptions(options,"",{...baseFilters,showUnavailable:true})).toHaveLength(2);
  });
});

describe("calendar topic search",()=>{
  const task={id:7,date:"2026-08-24",start_time:"18:00",duration:60,subject:"DILR",topic:"Cubes",title:"Cubes and binary logic",detail:"",resource:"",target_count:2,accuracy_target:80,priority:"High",completed:0,completion:0,actual_duration:0,manual:0,kind:"practice",topic_id:3,difficulty:"FOUNDATION",adaptive_reason:"",rescheduled:0,aimcat_schedule_id:null,time_foundation_test_id:2,time_foundation_test:{test_reference:"OBL1001812",provider_title:"Foundation - Cubes",} as StudyTask["time_foundation_test"],archived:0,completed_early:0,original_planned_date:null,actual_completion_date:null,reallocated_task_id:null,reallocated_from_date:null,reallocated_to_date:null,locked:0,pinned:0,resource_stages:[{provider:"TIME",title:"Cubes Foundation",description:"",platform_path:"Foundation → OBL1001812",resource_type:"FOUNDATION_TEST"} as StudyTask["resource_stages"][number]],result:null} as StudyTask;
  it("finds a future topic and a T.I.M.E. test reference",()=>{
    expect(searchCalendarTasks([task],"cubes")[0].id).toBe(7);
    expect(searchCalendarTasks([task],"OBL1001812")[0].id).toBe(7);
  });

  it("applies a task move without discarding material or reloading application data",()=>{
    const data={
      tasks:[task],
      timeFoundationSchedule:[{id:4,task_id:task.id,planned_date:task.date,manual_override:0}],
      meta:{plannedMinutes:task.duration,completedMinutes:0},
    } as AppData;
    const patch={
      refresh_required:false,task_ids:[task.id],grouped:false,date:"2026-08-25",
      tasks:[{id:task.id,date:"2026-08-25",start_time:"19:15",rescheduled:1}],
    };
    expect(isTaskMovePatch(patch)).toBe(true);
    const updated=applyTaskMovePatch(data,patch,"2026-08-24");
    expect(updated.tasks[0]).toMatchObject({id:task.id,date:"2026-08-25",start_time:"19:15",rescheduled:1});
    expect(updated.tasks[0].resource_stages).toBe(task.resource_stages);
    expect(updated.timeFoundationSchedule[0]).toMatchObject({planned_date:"2026-08-25",manual_override:1});
    expect(updated.meta.plannedMinutes).toBe(0);
    expect(updated.meta.completedMinutes).toBe(0);
  });
});
