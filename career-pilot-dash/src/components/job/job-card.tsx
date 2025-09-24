import { ExternalLink, Building2, MapPin, DollarSign } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "./status-badge";
import { AutoApplyButton } from "./auto-apply-button";
import type { Job } from "@/lib/types";

interface JobCardProps {
  job: Job;
  onExpand?: () => void;
  expanded?: boolean;
}

export function JobCard({ job, onExpand, expanded }: JobCardProps) {
  const getDomainFavicon = (domain: string) => {
    return `https://www.google.com/s2/favicons?domain=${domain}&sz=16`;
  };

  const getAtsColor = (tag: string) => {
    const colors = {
      ashby: "bg-blue-100 text-blue-800",
      greenhouse: "bg-green-100 text-green-800", 
      lever: "bg-purple-100 text-purple-800",
      linkedin: "bg-blue-100 text-blue-800",
      workday: "bg-orange-100 text-orange-800",
      other: "bg-gray-100 text-gray-800",
    };
    return colors[tag as keyof typeof colors] || colors.other;
  };

  return (
    <Card className="shadow-card hover:shadow-elegant transition-all duration-200">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-start space-x-3 flex-1">
            {/* Favicon */}
            <img
              src={getDomainFavicon(job.domain)}
              alt=""
              className="w-4 h-4 mt-1 flex-shrink-0"
              onError={(e) => {
                const target = e.target as HTMLImageElement;
                target.style.display = 'none';
              }}
            />
            
            {/* Job Info */}
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-foreground truncate">
                {job.title}
              </h3>
              {job.company && (
                <div className="flex items-center text-sm text-muted-foreground mt-1">
                  <Building2 className="w-3 h-3 mr-1" />
                  <span>{job.company}</span>
                </div>
              )}
              <div className="flex items-center text-sm text-muted-foreground mt-1">
                <span className="truncate">{job.domain}</span>
              </div>
            </div>
          </div>

          {/* Status */}
          <StatusBadge status={job.status} />
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-1 mt-2">
          {job.tags.map((tag) => (
            <Badge
              key={tag}
              variant="secondary"
              className={getAtsColor(tag)}
            >
              {tag.toUpperCase()}
            </Badge>
          ))}
        </div>
      </CardHeader>

      <CardContent className="pt-0">
        {/* Job Details */}
        {job.details && (
          <div className="flex flex-wrap gap-4 text-sm text-muted-foreground mb-3">
            {job.details.location && (
              <div className="flex items-center">
                <MapPin className="w-3 h-3 mr-1" />
                <span>{job.details.location}</span>
              </div>
            )}
            {job.details.salaryText && (
              <div className="flex items-center">
                <DollarSign className="w-3 h-3 mr-1" />
                <span>{job.details.salaryText}</span>
              </div>
            )}
          </div>
        )}

        {/* Progress Bar */}
        {job.progressPct !== undefined && job.progressPct > 0 && (
          <div className="mb-3">
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="text-muted-foreground">Progress</span>
              <span className="text-muted-foreground">{job.progressPct}%</span>
            </div>
            <div className="w-full bg-muted rounded-full h-2">
              <div
                className="bg-gradient-primary h-2 rounded-full transition-all duration-500"
                style={{ width: `${job.progressPct}%` }}
              />
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AutoApplyButton job={job} size="sm" />
            <Button variant="ghost" size="sm" asChild>
              <a href={job.url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="w-4 h-4 mr-1" />
                Open
              </a>
            </Button>
          </div>

          <div className="text-xs text-muted-foreground">
            Updated {new Date(job.lastUpdated).toLocaleString()}
          </div>
        </div>

        {/* Expanded Details */}
        {expanded && (
          <div className="mt-4 pt-4 border-t">
            <div className="space-y-2 text-sm">
              <div>
                <span className="font-medium text-muted-foreground">URL: </span>
                <a 
                  href={job.url}
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-primary hover:underline break-all"
                >
                  {job.url}
                </a>
              </div>
              {job.details?.via && (
                <div>
                  <span className="font-medium text-muted-foreground">Source: </span>
                  <span>{job.details.via}</span>
                </div>
              )}
              <div>
                <span className="font-medium text-muted-foreground">Created: </span>
                <span>{new Date(job.createdAt).toLocaleString()}</span>
              </div>
            </div>
          </div>
        )}

        {/* Expand Button */}
        {onExpand && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onExpand}
            className="w-full mt-2"
          >
            {expanded ? "Show Less" : "Show More"}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}