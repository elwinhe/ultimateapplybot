import { useState } from "react";
import { Plus, Filter, RefreshCw, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { JobTable } from "@/components/job/job-table";
import { useJobs, useAddJobUrl } from "@/hooks/use-jobs";
import { useToast } from "@/hooks/use-toast";

const Index = () => {
  const [addJobUrl, setAddJobUrl] = useState("");
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const { data: jobsResponse, isLoading, refetch } = useJobs();
  const addJobMutation = useAddJobUrl();
  const { toast } = useToast();

  const jobs = jobsResponse?.items || [];

  const handleAddJob = async () => {
    if (!addJobUrl.trim()) {
      toast({
        title: "URL Required",
        description: "Please enter a valid job URL",
        variant: "destructive",
      });
      return;
    }

    try {
      await addJobMutation.mutateAsync(addJobUrl.trim());
      setAddJobUrl("");
      setIsAddDialogOpen(false);
    } catch (error) {
      // Error is handled by the mutation
    }
  };

  const handleRefresh = () => {
    refetch();
    toast({
      title: "Refreshing jobs",
      description: "Fetching the latest job data...",
    });
  };

  if (jobs.length === 0 && !isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-center max-w-md mx-auto">
          <div className="w-16 h-16 bg-gradient-primary rounded-full flex items-center justify-center mx-auto mb-4">
            <Plus className="w-8 h-8 text-primary-foreground" />
          </div>
          <h1 className="mb-4 text-2xl font-bold">No Jobs Yet</h1>
          <p className="text-muted-foreground mb-6">
            Connect your email or add job URLs manually to get started with automated applications.
          </p>
          
          <div className="space-y-3">
            <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
              <DialogTrigger asChild>
                <Button size="lg" className="w-full">
                  <Plus className="w-4 h-4 mr-2" />
                  Add Job URL
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Add Job URL</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="job-url">Job URL</Label>
                    <Input
                      id="job-url"
                      placeholder="https://jobs.ashbyhr.com/company/role"
                      value={addJobUrl}
                      onChange={(e) => setAddJobUrl(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleAddJob()}
                    />
                  </div>
                  <Button 
                    onClick={handleAddJob}
                    disabled={addJobMutation.isPending}
                    className="w-full"
                  >
                    {addJobMutation.isPending ? "Adding..." : "Add to Queue"}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
            
            <p className="text-sm text-muted-foreground">
              Or connect your email in Settings to automatically detect job opportunities
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Job Dashboard</h1>
          <p className="text-muted-foreground">
            Track and manage your job applications
          </p>
        </div>
        
        <div className="flex items-center space-x-2">
          <Button variant="outline" onClick={handleRefresh}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Refresh
          </Button>
          
          <Button variant="outline">
            <Filter className="w-4 h-4 mr-2" />
            Filters
          </Button>
          
          <Button variant="outline">
            <Download className="w-4 h-4 mr-2" />
            Export
          </Button>
          
          <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="w-4 h-4 mr-2" />
                Add Job
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add Job URL</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <Label htmlFor="job-url">Job URL</Label>
                  <Input
                    id="job-url"
                    placeholder="https://jobs.ashbyhr.com/company/role"
                    value={addJobUrl}
                    onChange={(e) => setAddJobUrl(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAddJob()}
                  />
                  <p className="text-sm text-muted-foreground mt-1">
                    Supports Ashby, Greenhouse, Lever, LinkedIn, and more
                  </p>
                </div>
                <Button 
                  onClick={handleAddJob}
                  disabled={addJobMutation.isPending}
                  className="w-full"
                >
                  {addJobMutation.isPending ? "Adding..." : "Add to Queue"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Jobs Table */}
      <JobTable jobs={jobs} loading={isLoading} />
    </div>
  );
};

export default Index;
