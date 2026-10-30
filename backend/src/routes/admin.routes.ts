import { Router, Request, Response } from 'express';
import { prisma } from '../db';
import { authenticate } from '../middleware/auth';
import { authorize } from '../middleware/rbac';
import { auditLog } from '../middleware/audit';

const router = Router();
router.use(authenticate);

// GET /api/admin/users — list all users
router.get('/users', authorize('ADMIN'), async (_req: Request, res: Response): Promise<void> => {
  const users = await prisma.user.findMany({
    select: { id: true, name: true, email: true, role: true, isActive: true, createdAt: true },
    orderBy: { createdAt: 'asc' },
  });
  res.json({ users });
});

// PATCH /api/admin/users/:id/role — change a user's role
router.patch('/users/:id/role', authorize('ADMIN'), async (req: Request, res: Response): Promise<void> => {
  const { id } = req.params;
  const { role } = req.body;
  const validRoles = ['APPLICANT', 'OFFICER', 'MANAGER', 'FRAUD_ANALYST', 'AUDITOR', 'ADMIN'];
  if (!validRoles.includes(role)) {
    res.status(400).json({ error: `Invalid role. Must be one of: ${validRoles.join(', ')}` });
    return;
  }
  // Admin cannot grant themselves MANAGER
  if (id === req.user!.userId && role === 'MANAGER') {
    res.status(403).json({ error: 'Admin cannot grant themselves the MANAGER role', code: 'SELF_ESCALATION' });
    return;
  }
  const updated = await prisma.user.update({
    where: { id },
    data: { role },
    select: { id: true, name: true, email: true, role: true },
  });
  await auditLog(req.user!.userId, 'ROLE_CHANGE', undefined, { targetUserId: id, newRole: role });
  res.json({ user: updated });
});

// PATCH /api/admin/users/:id/status — activate/deactivate user
router.patch('/users/:id/status', authorize('ADMIN'), async (req: Request, res: Response): Promise<void> => {
  const { id } = req.params;
  const { isActive } = req.body;
  const updated = await prisma.user.update({
    where: { id },
    data: { isActive: Boolean(isActive) },
    select: { id: true, name: true, email: true, role: true, isActive: true },
  });
  await auditLog(req.user!.userId, isActive ? 'USER_ACTIVATED' : 'USER_DEACTIVATED', undefined, { targetUserId: id });
  res.json({ user: updated });
});

export default router;
