import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import type { Job, JobsResponse } from "@/lib/types";

export function useJobs(filters?: Record<string, any>) {
  return useQuery({
    queryKey: ["jobs", filters],
    queryFn: () => api.getJobs(filters),
    refetchInterval: 15000, // Refetch every 15 seconds
    staleTime: 10000, // Consider data stale after 10 seconds
  });
}

export function useAddJobUrl() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (url: string) => api.addJobUrl(url),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      toast({
        title: "Job added successfully",
        description: `Added "${data.title}" to the queue`,
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to add job",
        description: error.message,
        variant: "destructive",
      });
    },
  });
}

export function useAutoApplyJob() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (jobId: string) => api.autoApplyJob(jobId),
    onMutate: async (jobId) => {
      // Optimistic update
      await queryClient.cancelQueries({ queryKey: ["jobs"] });
      
      const previousJobs = queryClient.getQueryData(["jobs"]);
      
      queryClient.setQueryData(["jobs"], (old: JobsResponse | undefined) => {
        if (!old) return old;
        return {
          ...old,
          items: old.items.map((job) =>
            job.id === jobId
              ? { ...job, status: "in_progress" as const, progressPct: 10 }
              : job
          ),
        };
      });

      return { previousJobs };
    },
    onSuccess: (data, jobId) => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      toast({
        title: "Auto-apply started",
        description: `Started auto-applying for "${data.title}"`,
      });
    },
    onError: (error, jobId, context) => {
      // Revert optimistic update
      if (context?.previousJobs) {
        queryClient.setQueryData(["jobs"], context.previousJobs);
      }
      
      toast({
        title: "Auto-apply failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });
}

export function useJobFilters() {
  // This would typically use zustand or localStorage for persistence
  // For now, return a simple state management hook
  
  const filters = {
    query: "",
    ats: [] as string[],
    status: [] as string[],
    dateFrom: undefined as string | undefined,
    dateTo: undefined as string | undefined,
  };

  const setFilters = (newFilters: Partial<typeof filters>) => {
    // In a real app, this would update state and persist to localStorage
    console.log("Setting filters:", newFilters);
  };

  const clearFilters = () => {
    setFilters({
      query: "",
      ats: [],
      status: [],
      dateFrom: undefined,
      dateTo: undefined,
    });
  };

  return {
    filters,
    setFilters,
    clearFilters,
  };
}

// Hook for getting supported ATS tags for auto-apply
export function getSupportedAtsTags(): string[] {
  return ["ashby", "greenhouse", "lever"];
}

export function canAutoApply(job: Job): boolean {
  const supportedAts = getSupportedAtsTags();
  const hasSupported = job.tags.some(tag => supportedAts.includes(tag));
  const validStatus = ["ready", "error", "snoozed"].includes(job.status);
  return hasSupported && validStatus;
}