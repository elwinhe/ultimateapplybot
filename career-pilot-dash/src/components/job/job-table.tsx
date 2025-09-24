import { useState } from "react";
import { MoreHorizontal, ExternalLink, Grid3X3, List } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { JobCard } from "./job-card";
import { StatusBadge } from "./status-badge";
import { AutoApplyButton } from "./auto-apply-button";
import type { Job } from "@/lib/types";

interface JobTableProps {
  jobs: Job[];
  loading?: boolean;
}

type ViewMode = "table" | "grid";

export function JobTable({ jobs, loading }: JobTableProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRowExpansion = (jobId: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(jobId)) {
      newExpanded.delete(jobId);
    } else {
      newExpanded.add(jobId);
    }
    setExpandedRows(newExpanded);
  };

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

  if (loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-16 bg-muted rounded animate-pulse" />
        ))}
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">No jobs found</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* View Toggle */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">
          {jobs.length} {jobs.length === 1 ? "Job" : "Jobs"}
        </h2>
        <div className="flex items-center space-x-2">
          <Button
            variant={viewMode === "table" ? "default" : "ghost"}
            size="sm"
            onClick={() => setViewMode("table")}
          >
            <List className="w-4 h-4" />
          </Button>
          <Button
            variant={viewMode === "grid" ? "default" : "ghost"}
            size="sm"
            onClick={() => setViewMode("grid")}
          >
            <Grid3X3 className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Grid View */}
      {viewMode === "grid" && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              expanded={expandedRows.has(job.id)}
              onExpand={() => toggleRowExpansion(job.id)}
            />
          ))}
        </div>
      )}

      {/* Table View */}
      {viewMode === "table" && (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12"></TableHead>
                <TableHead>Job Title</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Tags</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Last Updated</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <TableRow key={job.id} className="cursor-pointer hover:bg-muted/50">
                  <TableCell>
                    <img
                      src={getDomainFavicon(job.domain)}
                      alt=""
                      className="w-4 h-4"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                      }}
                    />
                  </TableCell>
                  <TableCell>
                    <div>
                      <div className="font-medium truncate max-w-xs">
                        {job.title}
                      </div>
                      {job.details?.location && (
                        <div className="text-sm text-muted-foreground">
                          {job.details.location}
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="truncate max-w-xs">
                      {job.company || "-"}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">
                      {job.domain}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {job.tags.slice(0, 2).map((tag) => (
                        <Badge
                          key={tag}
                          variant="secondary"
                          className={`text-xs ${getAtsColor(tag)}`}
                        >
                          {tag.toUpperCase()}
                        </Badge>
                      ))}
                      {job.tags.length > 2 && (
                        <Badge variant="secondary" className="text-xs">
                          +{job.tags.length - 2}
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={job.status} />
                  </TableCell>
                  <TableCell>
                    {job.progressPct !== undefined && job.progressPct > 0 ? (
                      <div className="flex items-center space-x-2">
                        <div className="w-16 bg-muted rounded-full h-2">
                          <div
                            className="bg-gradient-primary h-2 rounded-full"
                            style={{ width: `${job.progressPct}%` }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {job.progressPct}%
                        </span>
                      </div>
                    ) : (
                      "-"
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="text-sm text-muted-foreground">
                      {new Date(job.lastUpdated).toLocaleDateString()}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center space-x-1">
                      <AutoApplyButton job={job} size="sm" />
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm">
                            <MoreHorizontal className="w-4 h-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <a href={job.url} target="_blank" rel="noopener noreferrer">
                              <ExternalLink className="w-4 h-4 mr-2" />
                              Open Job
                            </a>
                          </DropdownMenuItem>
                          <DropdownMenuItem 
                            onClick={() => toggleRowExpansion(job.id)}
                          >
                            {expandedRows.has(job.id) ? "Hide" : "Show"} Details
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}