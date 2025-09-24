# Ultimate Apply Bot - Frontend Dashboard

A production-ready React dashboard for automating job applications with intelligent email filtering and ATS integration.

## ✨ Features

### 🎯 **Job Tracking & Management**
- **Interactive Dashboard** - Clean table/grid views with real-time job status
- **Auto-Apply Integration** - One-click applications for Ashby, Greenhouse, and Lever
- **Smart Status Tracking** - Visual progress indicators and status badges
- **Bulk Operations** - Multi-select jobs for batch actions

### 📧 **Email Integration** 
- **Gmail & Outlook Support** - OAuth-based secure email connections
- **Intelligent Filtering** - Customizable rules to detect job opportunities
- **Real-time Monitoring** - Automatic job extraction from email notifications

### 📊 **Analytics & Activity**
- **Live Activity Feed** - Real-time event streaming with SSE/WebSocket support
- **Detailed Logging** - Track every job action and system event
- **Performance Metrics** - Success rates and application analytics

### ⚙️ **Advanced Settings**
- **Email Filter Builder** - Visual rule configuration interface
- **Integration Management** - Connect/disconnect email accounts
- **Cache Control** - Performance optimization and data management

## 🚀 Tech Stack

- **Framework**: React 18 + TypeScript + Vite
- **Styling**: TailwindCSS + shadcn/ui components
- **State Management**: TanStack Query + Zustand
- **Routing**: React Router v6
- **Validation**: Zod schemas for type safety
- **Authentication**: OAuth integration ready

## 🎨 Design System

### Professional Theme
- **Colors**: Blue-purple gradient palette with semantic tokens
- **Typography**: Modern, accessible font hierarchy  
- **Components**: Enhanced shadcn variants with custom styling
- **Animations**: Smooth transitions and micro-interactions

### Key Design Principles
- **Semantic Tokens**: All colors defined in CSS variables
- **Responsive**: Mobile-first design with keyboard accessibility
- **Performance**: Optimized with lazy loading and proper caching
- **Accessibility**: ARIA labels and focus management

## 📁 Project Structure

```
src/
├── components/           # Reusable UI components
│   ├── job/             # Job-specific components (cards, tables, etc.)
│   ├── layout/          # Layout components (sidebar, header)
│   └── ui/              # Base UI components (shadcn + enhanced)
├── hooks/               # Custom React hooks for API calls
├── lib/                 # Utilities, types, and API client
├── pages/               # Route components
└── assets/              # Static assets and images
```

## 🔧 Configuration

### Environment Setup

1. Copy the example environment file:
```bash
cp .env.local.example .env.local
```

2. Configure your settings:
```env
# Backend API URL
VITE_API_BASE_URL=https://your-backend.example.com

# Development mode with mock data
VITE_USE_MOCKS=true
```

### Backend Integration

The frontend expects these API endpoints:

```typescript
// Job Management
GET /api/jobs                    // List jobs with filters
POST /api/jobs/ingest-url       // Add job from URL
POST /api/jobs/{id}/auto-apply // Trigger auto-apply

// Email Settings  
GET /api/settings/email-filter   // Get filter configuration
POST /api/settings/email-filter // Update filter rules
POST /api/settings/email-filter/start // Start monitoring
POST /api/settings/email-filter/stop  // Stop monitoring

// Integrations
GET /api/integrations           // List connected services
POST /api/integrations/gmail/connect    // OAuth Gmail
POST /api/integrations/outlook/connect  // OAuth Outlook

// Real-time Updates
GET /api/stream                 // SSE for live updates
```

## 🛠 Development

### Prerequisites
- Node.js 18+ and npm
- Modern browser with ES2020 support

### Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production  
npm run build

# Preview production build
npm run preview
```

### Mock Development Mode

Enable `VITE_USE_MOCKS=true` to develop with realistic mock data:

- ✅ 4 sample jobs with different ATS types and statuses
- ✅ Mock activity feed with realistic events  
- ✅ Simulated API delays and error handling
- ✅ OAuth flow simulation for email connections

## 🔌 ATS Support Matrix

| Platform   | Detection | Auto-Apply | Notes                    |
|------------|-----------|------------|--------------------------|
| Ashby      | ✅        | ✅         | Full automation support  |
| Greenhouse | ✅        | ✅         | Full automation support  |
| Lever      | ✅        | ✅         | Full automation support  |  
| LinkedIn   | ✅        | ❌         | Detection only          |
| Workday    | ✅        | ❌         | Detection only          |

## 📱 Responsive Design

- **Mobile**: Optimized sidebar and touch-friendly interactions
- **Tablet**: Adaptive grid layouts and swipe gestures  
- **Desktop**: Full feature set with keyboard shortcuts
- **Accessibility**: Screen reader support and focus management

## 🔐 Security Features

- **OAuth Integration**: Secure email access without storing credentials
- **Input Validation**: Zod schemas for all API boundaries
- **XSS Prevention**: Sanitized rendering of user-generated content
- **CORS Protection**: Configurable API base URL validation

## 📊 Performance

- **React Query**: Smart caching and background updates
- **Lazy Loading**: Code splitting for optimal bundle size
- **Image Optimization**: Automatic favicon fetching and fallbacks
- **Real-time Updates**: Efficient SSE with polling fallback

## 🚦 Getting Started Checklist

1. ✅ **Environment Setup** - Configure `.env.local` 
2. ✅ **Backend Connection** - Set API base URL or enable mocks
3. ✅ **Email Integration** - Connect Gmail/Outlook in Settings
4. ✅ **Filter Configuration** - Set up email detection rules
5. ✅ **Test Auto-Apply** - Add a job URL and try auto-apply

## 📈 Roadmap

### Planned Features
- [ ] **Custom Cover Letters** - AI-generated personalized applications
- [ ] **Resume Management** - Multiple resume versions per job type
- [ ] **Saved Searches** - Persistent filter combinations  
- [ ] **Team Collaboration** - Share job pipelines with teammates
- [ ] **Mobile App** - Native iOS/Android applications

### Integration Expansion
- [ ] **Indeed** - Job detection and application support
- [ ] **AngelList** - Startup-focused job automation
- [ ] **Remote.co** - Remote work opportunity tracking
- [ ] **Company Careers Pages** - Direct integration support

---

**Ready to transform your job search?** Clone this repo and replace manual applications with intelligent automation. 🚀