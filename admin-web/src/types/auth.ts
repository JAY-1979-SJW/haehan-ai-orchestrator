export type UserRole = "viewer" | "admin" | "owner" | (string & {});

export interface CurrentUser {
  actor: string;
  role: UserRole;
}
