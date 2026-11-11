import { PipelineBoard } from "@/components/pipeline-board";

export default function PipelinePage() {
  return (
    <div className="px-4 py-6">
      <h1 className="mb-1 text-xl font-semibold">Pipeline</h1>
      <p className="mb-4 text-sm text-muted-foreground">Drag a card to change its status, or use the Move to menu on each card.</p>
      <PipelineBoard />
    </div>
  );
}
