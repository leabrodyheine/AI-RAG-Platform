import {
  Activity,
  Beaker,
  Bot,
  Boxes,
  ChevronsUpDown,
  Search,
} from "lucide-react";

import type { AppSection } from "../types/platform";
import { ServiceStatus } from "./ServiceStatus";

interface AppShellProps {
  activeSection: AppSection;
  children: React.ReactNode;
  onSectionChange: (section: AppSection) => void;
}

const navigation = [
  { id: "investigate" as const, label: "Investigate", icon: Search },
  { id: "evaluations" as const, label: "Evaluations", icon: Beaker },
  { id: "monitoring" as const, label: "Monitoring", icon: Activity },
];

export function AppShell({ activeSection, children, onSectionChange }: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <Boxes size={19} />
          </span>
          <span>
            <strong>RAG Control</strong>
            <small>Evaluation platform</small>
          </span>
        </div>

        <div className="workspace-picker">
          <span className="workspace-picker__icon">
            <Bot size={16} />
          </span>
          <span>
            <small>Workspace</small>
            <strong>Production lab</strong>
          </span>
          <ChevronsUpDown size={15} />
        </div>

        <nav className="primary-nav" aria-label="Primary navigation">
          <span className="nav-label">Workspace</span>
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              aria-current={activeSection === id ? "page" : undefined}
              className={activeSection === id ? "nav-item nav-item--active" : "nav-item"}
              key={id}
              onClick={() => onSectionChange(id)}
              type="button"
            >
              <Icon size={17} />
              {label}
            </button>
          ))}
        </nav>

        <div className="sidebar__footer">
          <ServiceStatus label="All systems" status="healthy" />
          <div className="user-card">
            <span className="avatar">PE</span>
            <span>
              <strong>Local operator</strong>
              <small>Platform engineer</small>
            </span>
          </div>
        </div>
      </aside>

      <div className="app-shell__content">{children}</div>
    </div>
  );
}
