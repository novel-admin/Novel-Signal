export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type ModuleMeta = {
  module: string;
  owner: "Akanksh" | "Palguna";
  status: "scaffolded";
};
