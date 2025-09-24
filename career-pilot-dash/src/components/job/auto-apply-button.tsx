import { Button } from "@/components/ui/button";
import { 
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Play, Loader2 } from "lucide-react";
import { useAutoApplyJob, canAutoApply, getSupportedAtsTags } from "@/hooks/use-jobs";
import type { Job } from "@/lib/types";

interface AutoApplyButtonProps {
  job: Job;
  size?: "sm" | "default";
}

export function AutoApplyButton({ job, size = "default" }: AutoApplyButtonProps) {
  const autoApplyMutation = useAutoApplyJob();
  const isEnabled = canAutoApply(job);
  const supportedAts = getSupportedAtsTags();
  
  const handleAutoApply = () => {
    if (isEnabled) {
      autoApplyMutation.mutate(job.id);
    }
  };

  const getTooltipMessage = () => {
    if (!job.tags.some(tag => supportedAts.includes(tag))) {
      return `Auto-apply only supports: ${supportedAts.join(", ")}. Found: ${job.tags.join(", ")}`;
    }
    
    if (!["ready", "error", "snoozed"].includes(job.status)) {
      return `Auto-apply available when status is "ready", "error", or "snoozed". Current: ${job.status}`;
    }

    return "Start auto-apply for this job";
  };

  const button = (
    <Button
      size={size}
      variant={isEnabled ? "default" : "secondary"}
      disabled={!isEnabled || autoApplyMutation.isPending}
      onClick={handleAutoApply}
      className="flex items-center space-x-2"
    >
      {autoApplyMutation.isPending ? (
        <Loader2 className="w-4 h-4 animate-spin" />
      ) : (
        <Play className="w-4 h-4" />
      )}
      <span>Auto Apply</span>
    </Button>
  );

  if (!isEnabled) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          {button}
        </TooltipTrigger>
        <TooltipContent>
          <p className="max-w-xs text-sm">{getTooltipMessage()}</p>
        </TooltipContent>
      </Tooltip>
    );
  }

  return button;
}