import { Badge } from "@/components/ui/badge";
import { 
  Clock, 
  Search, 
  CheckCircle2, 
  Loader2, 
  AlertTriangle, 
  XCircle, 
  Pause 
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { JobStatus } from "@/lib/types";

interface StatusBadgeProps {
  status: JobStatus;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const getStatusConfig = (status: JobStatus) => {
    switch (status) {
      case "queued":
        return {
          icon: Clock,
          label: "Queued",
          variant: "secondary" as const,
          className: "text-muted-foreground"
        };
      case "parsing":
        return {
          icon: Search,
          label: "Parsing",
          variant: "secondary" as const, 
          className: "text-primary animate-pulse"
        };
      case "ready":
        return {
          icon: CheckCircle2,
          label: "Ready",
          variant: "secondary" as const,
          className: "text-success"
        };
      case "in_progress":
        return {
          icon: Loader2,
          label: "In Progress",
          variant: "secondary" as const,
          className: "text-primary animate-spin"
        };
      case "needs_info":
        return {
          icon: AlertTriangle,
          label: "Needs Info",
          variant: "secondary" as const,
          className: "text-warning"
        };
      case "submitted":
        return {
          icon: CheckCircle2,
          label: "Submitted",
          variant: "secondary" as const,
          className: "text-success"
        };
      case "error":
        return {
          icon: XCircle,
          label: "Error",
          variant: "destructive" as const,
          className: "text-destructive-foreground"
        };
      case "snoozed":
        return {
          icon: Pause,
          label: "Snoozed", 
          variant: "secondary" as const,
          className: "text-muted-foreground"
        };
      default:
        return {
          icon: Clock,
          label: "Unknown",
          variant: "secondary" as const,
          className: "text-muted-foreground"
        };
    }
  };

  const config = getStatusConfig(status);
  const Icon = config.icon;

  return (
    <Badge 
      variant={config.variant}
      className={cn("flex items-center space-x-1", className)}
    >
      <Icon className={cn("w-3 h-3", config.className)} />
      <span>{config.label}</span>
    </Badge>
  );
}