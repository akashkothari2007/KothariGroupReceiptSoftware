const ROLE_HIERARCHY = ['accountant', 'delegate', 'manager', 'admin']

export function hasRole(userRole, minimum) {
  return ROLE_HIERARCHY.indexOf(userRole) >= ROLE_HIERARCHY.indexOf(minimum)
}
