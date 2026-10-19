/**
 * Centralized developer team metadata for Mentor AI.
 * Team: Code ArenaX
 */

export interface TeamMember {
  id: string;
  name: string;
  role?: string;
  bio?: string;
  avatarUrl?: string;
  githubUrl: string;
  linkedinUrl: string;
  contributions?: string[];
}

export interface TeamInfo {
  name: string;
  tagline: string;
  description: string;
  logoUrl?: string;
  members: TeamMember[];
}

export const TEAM_INFO: TeamInfo = {
  name: "Code ArenaX",
  tagline: "Code. Compete. Conquer.",
  description:
    "The engineering team behind Mentor AI — architecting autonomous educational agents, proactive schedule intelligence, and deterministic academic copilots.",
  logoUrl: "/team/codearenax-logo.png",
  members: [
    {
      id: "alfi",
      name: "Alfi Shahrin Talukder",
      role: "Full-Stack & AI Systems Engineer",
      bio: "Specializing in full-stack architecture, multimodal Gemini copilot orchestration, and deterministic scheduling intelligence.",
      avatarUrl: "/team/alfi.jpg",
      githubUrl: "https://github.com/Alfi-svg",
      linkedinUrl:
        "https://www.linkedin.com/in/alfi-shahrin-talukder-a68450370/?isSelfProfile=true",
      contributions: [
        "Autonomous Gemini Copilot pipeline",
        "Proactive Daily Briefing engine",
        "Full-Stack security & architecture",
      ],
    },
    {
      id: "samiul",
      name: "Samiul Islam",
      role: "Software & Systems Engineer",
      bio: "Focusing on reliable calendar integrations, task orchestration pipelines, and responsive modern user experiences.",
      avatarUrl: "/team/samiul.png",
      githubUrl: "https://github.com/samiulxr2",
      linkedinUrl: "https://www.linkedin.com/in/samiulxr2/",
      contributions: [
        "Google Calendar synchronization",
        "Task management & scheduling engine",
        "Frontend components & responsive UI",
      ],
    },
  ],
};
