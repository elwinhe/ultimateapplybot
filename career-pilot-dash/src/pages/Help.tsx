import { HelpCircle, CheckCircle, XCircle, AlertTriangle, ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

const Help = () => {
  const supportedAts = [
    { name: "Ashby", status: "full", description: "Full auto-apply support" },
    { name: "Greenhouse", status: "full", description: "Full auto-apply support" },
    { name: "Lever", status: "full", description: "Full auto-apply support" },
    { name: "LinkedIn", status: "partial", description: "Detection only, manual apply required" },
    { name: "Workday", status: "partial", description: "Detection only, manual apply required" },
  ];

  const faqs = [
    {
      question: "Which job boards support auto-apply?",
      answer: "Currently, we support automatic applications for Ashby, Greenhouse, and Lever. LinkedIn and Workday jobs are detected but require manual application."
    },
    {
      question: "How does email filtering work?",
      answer: "Connect your Gmail or Outlook account and we'll scan your emails for job notifications, extracting job URLs automatically based on your configured rules."
    },
    {
      question: "Is my data secure?",
      answer: "Yes, we use industry-standard OAuth for email access and never store your email credentials. Job data is encrypted and processed securely."
    },
    {
      question: "What happens if an auto-apply fails?",
      answer: "Failed applications are marked with error status. Check the Activity feed for details and retry manually if needed."
    },
    {
      question: "Can I customize the application process?",
      answer: "Currently, auto-apply uses standard application flows. Custom cover letters and resume selection will be available in future updates."
    }
  ];

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "full":
        return <CheckCircle className="w-4 h-4 text-green-600" />;
      case "partial":
        return <AlertTriangle className="w-4 h-4 text-yellow-600" />;
      case "none":
        return <XCircle className="w-4 h-4 text-red-600" />;
      default:
        return <HelpCircle className="w-4 h-4 text-gray-600" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const configs = {
      full: { label: "Full Support", className: "bg-green-100 text-green-800" },
      partial: { label: "Partial Support", className: "bg-yellow-100 text-yellow-800" },
      none: { label: "Not Supported", className: "bg-red-100 text-red-800" },
    };
    const config = configs[status as keyof typeof configs] || configs.none;
    
    return (
      <Badge variant="secondary" className={config.className}>
        {config.label}
      </Badge>
    );
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center space-x-2">
          <HelpCircle className="w-6 h-6" />
          <span>Help & Support</span>
        </h1>
        <p className="text-muted-foreground">
          Learn how to use Ultimate Apply Bot effectively
        </p>
      </div>

      {/* ATS Support Status */}
      <Card>
        <CardHeader>
          <CardTitle>Supported Job Boards</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {supportedAts.map((ats) => (
              <div key={ats.name} className="flex items-center justify-between p-3 border rounded-lg">
                <div className="flex items-center space-x-3">
                  {getStatusIcon(ats.status)}
                  <div>
                    <h3 className="font-medium">{ats.name}</h3>
                    <p className="text-sm text-muted-foreground">{ats.description}</p>
                  </div>
                </div>
                {getStatusBadge(ats.status)}
              </div>
            ))}
          </div>
          
          <div className="mt-4 p-4 bg-muted rounded-lg">
            <p className="text-sm">
              <strong>Note:</strong> Auto-apply is only available for Ashby, Greenhouse, and Lever. 
              Other platforms will be detected but require manual application.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Getting Started */}
      <Card>
        <CardHeader>
          <CardTitle>Getting Started</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            <div className="flex items-start space-x-3">
              <div className="w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm font-medium">
                1
              </div>
              <div>
                <h3 className="font-medium">Connect Your Email</h3>
                <p className="text-sm text-muted-foreground">
                  Go to Settings and connect Gmail or Outlook to automatically detect job emails
                </p>
              </div>
            </div>
            
            <div className="flex items-start space-x-3">
              <div className="w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm font-medium">
                2
              </div>
              <div>
                <h3 className="font-medium">Configure Filtering Rules</h3>
                <p className="text-sm text-muted-foreground">
                  Set up email filters to automatically identify job notifications
                </p>
              </div>
            </div>
            
            <div className="flex items-start space-x-3">
              <div className="w-6 h-6 bg-primary text-primary-foreground rounded-full flex items-center justify-center text-sm font-medium">
                3
              </div>
              <div>
                <h3 className="font-medium">Start Auto-Applying</h3>
                <p className="text-sm text-muted-foreground">
                  Use the Auto Apply button on supported job boards (Ashby, Greenhouse, Lever)
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* FAQ */}
      <Card>
        <CardHeader>
          <CardTitle>Frequently Asked Questions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            {faqs.map((faq, index) => (
              <div key={index}>
                <h3 className="font-medium mb-2">{faq.question}</h3>
                <p className="text-sm text-muted-foreground">{faq.answer}</p>
                {index < faqs.length - 1 && <Separator className="mt-4" />}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Support */}
      <Card>
        <CardHeader>
          <CardTitle>Need More Help?</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            If you're experiencing issues or have questions not covered here, we're here to help.
          </p>
          
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" asChild>
              <a href="mailto:support@ultimateapplybot.com" target="_blank" rel="noopener noreferrer">
                Email Support
                <ExternalLink className="w-4 h-4 ml-2" />
              </a>
            </Button>
            
            <Button variant="outline" asChild>
              <a href="https://docs.ultimateapplybot.com" target="_blank" rel="noopener noreferrer">
                Documentation
                <ExternalLink className="w-4 h-4 ml-2" />
              </a>
            </Button>
            
            <Button variant="outline" asChild>
              <a href="https://github.com/ultimateapplybot/issues" target="_blank" rel="noopener noreferrer">
                Report Bug
                <ExternalLink className="w-4 h-4 ml-2" />
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Help;