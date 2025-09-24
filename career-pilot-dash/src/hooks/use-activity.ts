import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ActivityResponse } from "@/lib/types";

export function useActivity(filters?: Record<string, any>) {
  return useQuery({
    queryKey: ["activity", filters],
    queryFn: () => api.getActivity(filters),
    refetchInterval: 5000, // Refetch every 5 seconds for live updates
    staleTime: 2000, // Consider data stale after 2 seconds
  });
}

export function useActivityStream() {
  // This would implement SSE/WebSocket connection for real-time updates
  // For now, return a mock implementation
  
  const connect = () => {
    // Mock SSE connection
    console.log("Connecting to activity stream...");
    
    // In a real implementation:
    // const eventSource = new EventSource('/api/stream');
    // eventSource.onmessage = (event) => {
    //   const data = JSON.parse(event.data);
    //   // Handle real-time updates
    // };
  };

  const disconnect = () => {
    console.log("Disconnecting from activity stream...");
  };

  return {
    connect,
    disconnect,
    isConnected: false, // Mock state
  };
}