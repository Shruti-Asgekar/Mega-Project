import { Request, Response, NextFunction } from 'express';

// authorize(...roles) — middleware factory checking role membership
export function authorize(...roles: string[]) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ error: 'Authentication required', code: 'NO_TOKEN' });
      return;
    }
    if (!roles.includes(req.user.role)) {
      res.status(403).json({
        error: 'You do not have permission to perform this action',
        code: 'FORBIDDEN',
        required: roles,
        current: req.user.role,
      });
      return;
    }
    next();
  };
}

// ownsApplication — applicants can only access their own applications
export function ownsApplication(applicationApplicantId: string) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.user) {
      res.status(401).json({ error: 'Authentication required', code: 'NO_TOKEN' });
      return;
    }
    if (req.user.role === 'APPLICANT' && req.user.userId !== applicationApplicantId) {
      res.status(403).json({ error: 'Access denied to this application', code: 'NOT_OWNER' });
      return;
    }
    next();
  };
}
