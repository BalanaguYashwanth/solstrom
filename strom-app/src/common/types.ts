// common/types.ts
export interface Message {
  text: string;
  sender: "user" | "bot";
  projectData?: ProjectAgentResponse;
}

export interface Source {
  source_name?: string;
  source_url?: string;
}

export interface ProjectAgentResponse {
  points: string[];
  is_greeting: boolean;
  exists_in_data: boolean;
  exists_elsewhere: boolean;
  relevant_projects?: string[];
  sources?: any[];
}

export interface PopupProps {
  open: boolean;
  heading?: string;
  message: string;
  onClose: () => void;
  actions?: React.ReactNode;
}