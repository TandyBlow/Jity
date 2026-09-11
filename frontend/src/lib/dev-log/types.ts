export type DevLogEntry = {
  id: string;
  date: string;
  title: string;
  summary: string;
  developer: string;
  areas: string[];
  changes: string[];
  relatedFiles: string[];
  nextSteps?: string[];
};
