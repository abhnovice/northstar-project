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
