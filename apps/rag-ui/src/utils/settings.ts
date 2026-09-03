export const API_URL = import.meta.env.VITE_API_URL;
// Navigation choices for the legacy debug UI; the backend policy remains authoritative.
export const USER_ROLES = ['doctor', 'nurse', 'analyst', 'manager', 'agent'] as const;
export type UserRole = (typeof USER_ROLES)[number];
