import { useState } from "react";
import { Activity as ActivityIcon, Filter, RefreshCw, Clock, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useActivity } from "@/hooks/use-activity";
import type { EventLog } from "@/lib/types";

const Activity = () => {
  const [eventFilter, setEventFilter] = useState<string>("all");
  const { data: activityResponse, isLoading, refetch } = useActivity({ 
    type: eventFilter === "all" ? undefined : eventFilter 
  });

  const events = activityResponse?.items || [];

  const getEventIcon = (type: EventLog["type"]) => {
    switch (type) {
      case "ingest":
        return <Clock className="w-4 h-4 text-blue-600" />;
      case "filter_start":
      case "filter_stop":
        return <Filter className="w-4 h-4 text-purple-600" />;
      case "queue":
        return <Clock className="w-4 h-4 text-orange-600" />;
      case "auto_apply":
        return <ActivityIcon className="w-4 h-4 text-green-600" />;
      case "status":
        return <CheckCircle2 className="w-4 h-4 text-blue-600" />;
      case "error":
        return <XCircle className="w-4 h-4 text-red-600" />;
      default:
        return <Clock className="w-4 h-4 text-gray-600" />;
    }
  };

  const getEventColor = (type: EventLog["type"]) => {
    switch (type) {
      case "ingest":
        return "bg-blue-100 text-blue-800";
      case "filter_start":
      case "filter_stop":
        return "bg-purple-100 text-purple-800";
      case "queue":
        return "bg-orange-100 text-orange-800";
      case "auto_apply":
        return "bg-green-100 text-green-800";
      case "status":
        return "bg-blue-100 text-blue-800";
      case "error":
        return "bg-red-100 text-red-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  const formatEventType = (type: EventLog["type"]) => {
    const labels = {
      ingest: "Job Ingested",
      filter_start: "Filtering Started",
      filter_stop: "Filtering Stopped", 
      queue: "Queued",
      auto_apply: "Auto Apply",
      status: "Status Update",
      error: "Error",
    };
    return labels[type] || type;
  };

  const formatRelativeTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-16 bg-muted rounded animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center space-x-2">
            <ActivityIcon className="w-6 h-6" />
            <span>Activity Feed</span>
          </h1>
          <p className="text-muted-foreground">
            Real-time log of system events and job processing
          </p>
        </div>
        
        <div className="flex items-center space-x-2">
          <Select value={eventFilter} onValueChange={setEventFilter}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Filter events" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Events</SelectItem>
              <SelectItem value="ingest">Job Ingested</SelectItem>
              <SelectItem value="auto_apply">Auto Apply</SelectItem>
              <SelectItem value="error">Errors</SelectItem>
              <SelectItem value="filter_start">Filter Events</SelectItem>
            </SelectContent>
          </Select>
          
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Live Indicator */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <span className="text-sm font-medium">Live Activity Feed</span>
            </div>
            <Badge variant="secondary" className="bg-green-100 text-green-800">
              {events.length} events
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Activity List */}
      {events.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <ActivityIcon className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium mb-2">No Activity Yet</h3>
            <p className="text-muted-foreground">
              Events will appear here as jobs are processed and applications are submitted.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {events.map((event) => (
            <Card key={event.id} className="hover:shadow-card transition-shadow">
              <CardContent className="p-4">
                <div className="flex items-start space-x-3">
                  <div className="flex-shrink-0 mt-1">
                    {getEventIcon(event.type)}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Badge 
                          variant="secondary" 
                          className={getEventColor(event.type)}
                        >
                          {formatEventType(event.type)}
                        </Badge>
                        {event.jobId && (
                          <Badge variant="outline" className="text-xs">
                            Job #{event.jobId.slice(-6)}
                          </Badge>
                        )}
                      </div>
                      <span className="text-sm text-muted-foreground">
                        {formatRelativeTime(event.createdAt)}
                      </span>
                    </div>
                    
                    <p className="mt-1 text-foreground">{event.message}</p>
                    
                    {event.data && Object.keys(event.data).length > 0 && (
                      <details className="mt-2">
                        <summary className="text-sm text-muted-foreground cursor-pointer hover:text-foreground">
                          View Details
                        </summary>
                        <pre className="mt-2 text-xs bg-muted p-3 rounded overflow-x-auto">
                          {JSON.stringify(event.data, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

export default Activity;