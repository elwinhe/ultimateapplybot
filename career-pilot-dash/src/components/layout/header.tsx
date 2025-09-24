import { Search, Mail, MailCheck, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useIntegrations } from "@/hooks/use-integrations";

export function Header() {
  const { data: integrations = [] } = useIntegrations();
  
  const gmailIntegration = integrations.find(i => i.type === "gmail");
  const outlookIntegration = integrations.find(i => i.type === "outlook");

  const handleConnectGmail = () => {
    // This would trigger the OAuth flow
    console.log("Connecting Gmail...");
  };

  const handleConnectOutlook = () => {
    // This would trigger the OAuth flow 
    console.log("Connecting Outlook...");
  };

  return (
    <header className="flex items-center justify-between px-6 py-3 bg-card border-b">
      {/* Search */}
      <div className="flex items-center flex-1 max-w-md">
        <div className="relative w-full">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search jobs, companies, or URLs..."
            className="pl-10"
          />
        </div>
      </div>

      {/* Email Connections & User Menu */}
      <div className="flex items-center space-x-4">
        {/* Gmail Connection */}
        {gmailIntegration?.connected ? (
          <Badge variant="secondary" className="flex items-center space-x-1">
            <MailCheck className="w-3 h-3" />
            <span>Gmail Connected</span>
          </Badge>
        ) : (
          <Button variant="outline" size="sm" onClick={handleConnectGmail}>
            <Mail className="w-4 h-4 mr-2" />
            Connect Gmail
          </Button>
        )}

        {/* Outlook Connection */}
        {outlookIntegration?.connected ? (
          <Badge variant="secondary" className="flex items-center space-x-1">
            <MailCheck className="w-3 h-3" />
            <span>Outlook Connected</span>
          </Badge>
        ) : (
          <Button variant="outline" size="sm" onClick={handleConnectOutlook}>
            <Mail className="w-4 h-4 mr-2" />
            Connect Outlook
          </Button>
        )}

        {/* User Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="flex items-center space-x-2">
              <div className="w-6 h-6 bg-gradient-primary rounded-full flex items-center justify-center">
                <User className="w-3 h-3 text-primary-foreground" />
              </div>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem>
              <User className="w-4 h-4 mr-2" />
              Profile Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive">
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}