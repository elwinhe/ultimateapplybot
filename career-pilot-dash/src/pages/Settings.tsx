import { useState } from "react";
import { Mail, MailCheck, Shield, Trash2, Play, Pause } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { 
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { 
  useIntegrations, 
  useConnectGmail, 
  useConnectOutlook,
  useDisconnectGmail,
  useDisconnectOutlook 
} from "@/hooks/use-integrations";
import { 
  useEmailSettings, 
  useStartEmailFiltering, 
  useStopEmailFiltering, 
  useClearCache 
} from "@/hooks/use-settings";
import { useToast } from "@/hooks/use-toast";

const Settings = () => {
  const { data: integrations = [] } = useIntegrations();
  const { data: emailSettings } = useEmailSettings();
  const { toast } = useToast();
  
  const connectGmail = useConnectGmail();
  const connectOutlook = useConnectOutlook();
  const disconnectGmail = useDisconnectGmail();
  const disconnectOutlook = useDisconnectOutlook();
  const startFiltering = useStartEmailFiltering();
  const stopFiltering = useStopEmailFiltering();
  const clearCache = useClearCache();

  const [notificationsEnabled, setNotificationsEnabled] = useState(true);

  const gmailIntegration = integrations.find(i => i.type === "gmail");
  const outlookIntegration = integrations.find(i => i.type === "outlook");

  const handleToggleFiltering = async () => {
    if (emailSettings?.isRunning) {
      await stopFiltering.mutateAsync();
    } else {
      await startFiltering.mutateAsync();
    }
  };

  const handleClearCache = async () => {
    await clearCache.mutateAsync();
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted-foreground">
          Configure your Ultimate Apply Bot preferences and integrations
        </p>
      </div>

      {/* Email Integrations */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Mail className="w-5 h-5" />
            <span>Email Integrations</span>
          </CardTitle>
          <CardDescription>
            Connect your email accounts to automatically detect job opportunities
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Gmail Integration */}
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center">
                <Mail className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <h3 className="font-medium">Gmail</h3>
                {gmailIntegration?.connected ? (
                  <div className="flex items-center space-x-2">
                    <Badge variant="secondary" className="bg-green-100 text-green-800">
                      <MailCheck className="w-3 h-3 mr-1" />
                      Connected
                    </Badge>
                    <span className="text-sm text-muted-foreground">
                      {gmailIntegration.email}
                    </span>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Not connected</p>
                )}
              </div>
            </div>
            
            {gmailIntegration?.connected ? (
              <Button 
                variant="outline" 
                onClick={() => disconnectGmail.mutate()}
                disabled={disconnectGmail.isPending}
              >
                Disconnect
              </Button>
            ) : (
              <Button 
                onClick={() => connectGmail.mutate()}
                disabled={connectGmail.isPending}
              >
                Connect Gmail
              </Button>
            )}
          </div>

          {/* Outlook Integration */}
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                <Mail className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h3 className="font-medium">Microsoft Outlook</h3>
                {outlookIntegration?.connected ? (
                  <div className="flex items-center space-x-2">
                    <Badge variant="secondary" className="bg-green-100 text-green-800">
                      <MailCheck className="w-3 h-3 mr-1" />
                      Connected
                    </Badge>
                    <span className="text-sm text-muted-foreground">
                      {outlookIntegration.email}
                    </span>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Not connected</p>
                )}
              </div>
            </div>
            
            {outlookIntegration?.connected ? (
              <Button 
                variant="outline"
                onClick={() => disconnectOutlook.mutate()}
                disabled={disconnectOutlook.isPending}
              >
                Disconnect
              </Button>
            ) : (
              <Button 
                onClick={() => connectOutlook.mutate()}
                disabled={connectOutlook.isPending}
              >
                Connect Outlook
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Email Filtering */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Shield className="w-5 h-5" />
              <span>Email Filtering</span>
            </div>
            {emailSettings?.isRunning && (
              <Badge variant="secondary" className="bg-green-100 text-green-800">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse mr-2" />
                Active
              </Badge>
            )}
          </CardTitle>
          <CardDescription>
            Configure automatic job detection from your emails
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium">Email Monitoring</h3>
              <p className="text-sm text-muted-foreground">
                Automatically scan emails for job opportunities
              </p>
            </div>
            <Button
              variant={emailSettings?.isRunning ? "destructive" : "default"}
              onClick={handleToggleFiltering}
              disabled={startFiltering.isPending || stopFiltering.isPending}
            >
              {emailSettings?.isRunning ? (
                <>
                  <Pause className="w-4 h-4 mr-2" />
                  Stop Filtering
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-2" />
                  Start Filtering
                </>
              )}
            </Button>
          </div>

          <Separator />

          <div className="space-y-2">
            <h4 className="font-medium">Filtering Rules</h4>
            <p className="text-sm text-muted-foreground">
              {emailSettings?.rules.length || 0} rules configured
            </p>
            <Button variant="outline" size="sm">
              Configure Rules
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Notifications */}
      <Card>
        <CardHeader>
          <CardTitle>Notifications</CardTitle>
          <CardDescription>
            Control when and how you receive notifications
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-medium">Desktop Notifications</h3>
              <p className="text-sm text-muted-foreground">
                Get notified when jobs are found or applications are submitted
              </p>
            </div>
            <Switch
              checked={notificationsEnabled}
              onCheckedChange={setNotificationsEnabled}
            />
          </div>
        </CardContent>
      </Card>

      {/* Cache Management */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Trash2 className="w-5 h-5" />
            <span>Cache Management</span>
          </CardTitle>
          <CardDescription>
            Clear cached data to reset the application state
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive">
                <Trash2 className="w-4 h-4 mr-2" />
                Clear All Cache
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Clear Cache</AlertDialogTitle>
                <AlertDialogDescription>
                  This will clear all cached job data, settings, and temporary files. 
                  Your integrations and saved settings will remain intact.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction 
                  onClick={handleClearCache}
                  disabled={clearCache.isPending}
                >
                  {clearCache.isPending ? "Clearing..." : "Clear Cache"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardContent>
      </Card>
    </div>
  );
};

export default Settings;