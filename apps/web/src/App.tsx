import { useState } from "react";

import { AppShell } from "./components/AppShell";
import { ChatWorkspace } from "./features/chat/ChatWorkspace";
import { EvaluationWorkspace } from "./features/evaluations/EvaluationWorkspace";
import { MonitoringWorkspace } from "./features/monitoring/MonitoringWorkspace";
import type { AppSection } from "./types/platform";

export function App() {
  const [activeSection, setActiveSection] = useState<AppSection>("investigate");

  const workspace = {
    investigate: <ChatWorkspace />,
    evaluations: <EvaluationWorkspace />,
    monitoring: <MonitoringWorkspace />,
  }[activeSection];

  return (
    <AppShell activeSection={activeSection} onSectionChange={setActiveSection}>
      {workspace}
    </AppShell>
  );
}
