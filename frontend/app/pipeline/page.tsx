import { PageHeader } from "@/components/page-header";
import { PipelineBoard } from "@/components/pipeline-board";

export default function PipelinePage() {
  return (
    <div>
      <PageHeader title="Pipeline" description="Drag a card to change its status, or use the Move to menu on each card." />
      <PipelineBoard />
    </div>
  );
}
