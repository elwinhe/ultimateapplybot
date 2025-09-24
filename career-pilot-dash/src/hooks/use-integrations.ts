import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import type { Integration } from "@/lib/types";

export function useIntegrations() {
  return useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.getIntegrations(),
    refetchInterval: 30000, // Refetch every 30 seconds
  });
}

export function useConnectGmail() {
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => api.connectGmail(),
    onSuccess: (data) => {
      // Redirect to OAuth URL
      window.location.href = data.redirectUrl;
    },
    onError: (error) => {
      toast({
        title: "Failed to connect Gmail",
        description: error.message,
        variant: "destructive",
      });
    },
  });
}

export function useConnectOutlook() {
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => api.connectOutlook(),
    onSuccess: (data) => {
      // Redirect to OAuth URL
      window.location.href = data.redirectUrl;
    },
    onError: (error) => {
      toast({
        title: "Failed to connect Outlook",
        description: error.message,
        variant: "destructive",
      });
    },
  });
}

export function useDisconnectGmail() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => api.disconnectGmail(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      toast({
        title: "Gmail disconnected",
        description: "Your Gmail integration has been disconnected successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to disconnect Gmail",
        description: error.message,
        variant: "destructive",
      });
    },
  });
}

export function useDisconnectOutlook() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: () => api.disconnectOutlook(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      toast({
        title: "Outlook disconnected",
        description: "Your Outlook integration has been disconnected successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to disconnect Outlook",
        description: error.message,
        variant: "destructive",
      });
    },
  });
}