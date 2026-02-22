/**
 * Utility functions for the TypeScript sample fixture.
 */

export interface User {
  id: number;
  name: string;
  email: string;
}

export class UserService {
  private users: User[] = [];

  /**
   * Add a new user to the service.
   */
  addUser(user: User): void {
    this.users.push(user);
  }

  /**
   * Find a user by their ID.
   */
  findById(id: number): User | undefined {
    return this.users.find((u) => u.id === id);
  }

  getCount(): number {
    return this.users.length;
  }
}

/**
 * Format a user's display name.
 */
export function formatDisplayName(user: User): string {
  return `${user.name} <${user.email}>`;
}

export async function fetchUser(url: string, id: number): Promise<User> {
  const response = await fetch(`${url}/users/${id}`);
  return response.json();
}
