import { Request, Response, NextFunction } from 'express';

export function errorHandler(err: Error, _req: Request, res: Response, _next: NextFunction): void {
  console.error('[ERROR]', err.message);
  res.status(500).json({
    error: 'An internal error occurred. Please try again.',
    code: 'INTERNAL_ERROR',
  });
}
