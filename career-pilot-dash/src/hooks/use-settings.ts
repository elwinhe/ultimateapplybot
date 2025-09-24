import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import type { EmailFilterSettings } from "@/lib/types";

export function useEmailSettings() {
  return useQuery({
    queryKey: ["email-settings"],
    queryFn: () => api.getEmailSettings(),
    refetchInterval: 10000, // Refetch every 10 seconds to get live status
  });
}

export function useUpdateEmailSettings() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (settings: EmailFilterSettings) => api.updateEmailSettings(settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["email-settings"] });
      toast({
        title: "Settings updated",
        description: "Email filter settings have been saved successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to update settings",
        description: error.message,
        variant: "destructive",
      });
    },
  });
}

export function useStartEmailFiltering() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => api.startEmailFiltering(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["email-settings"] });
      toast({
        title: "Email filtering started",
        description: "Now monitoring your email for job opportunities.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to start email filtering", 
        description: error.message,
        variant: "destructive",
      });
    },
  });
}

export function useStopEmailFiltering() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => api.stopEmailFiltering(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["email-settings"] });
      toast({
        title: "Email filtering stopped",
        description: "Email monitoring has been paused.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to stop email filtering",
        description: error.message,
        variant: "destructive",
      });
    },
  });
}

export function useClearCache() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => api.clearCache(),
    onSuccess: () => {
      // Invalidate all queries to refresh data
      queryClient.invalidateQueries();
      toast({
        title: "Cache cleared",
        description: "All cached data has been cleared successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to clear cache",
        description: error.message,
        variant: "destructive",
      });
    },
  });
}