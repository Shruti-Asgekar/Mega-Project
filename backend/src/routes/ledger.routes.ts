import { Router, Request, Response } from 'express';
import crypto from 'crypto';
import fs from 'fs';
import { prisma } from '../db';
import { authenticate } from '../middleware/auth';
import { authorize } from '../middleware/rbac';

const router = Router();
router.use(authenticate);

// GET /api/ledger/verify/:documentId — verify hash chain integrity
router.get('/verify/:documentId', authorize('OFFICER', 'MANAGER', 'AUDITOR', 'FRAUD_ANALYST'), async (req: Request, res: Response): Promise<void> => {
  const { documentId } = req.params;
  const doc = await prisma.document.findUnique({ where: { id: documentId } });
  if (!doc) { res.status(404).json({ error: 'Document not found' }); return; }
  const entry = await prisma.ledgerEntry.findUnique({ where: { documentId } });
  if (!entry) { res.json({ verified: false, reason: 'No ledger entry exists for this document yet' }); return; }

  // Re-hash the file on disk
  let currentHash = 'FILE_MISSING';
  if (fs.existsSync(doc.filePath)) {
    const data = fs.readFileSync(doc.filePath);
    currentHash = crypto.createHash('sha256').update(data).digest('hex');
  }
  const fileIntact = currentHash === entry.fileSha256;

  // Recompute entry hash to verify chain
  const recomputed = crypto
    .createHash('sha256')
    .update(`${entry.index}:${entry.documentId}:${entry.fileSha256}:${entry.prevHash}`)
    .digest('hex');
  const chainIntact = recomputed === entry.entryHash;

  res.json({
    verified: fileIntact && chainIntact,
    fileIntact,
    chainIntact,
    documentId,
    ledgerIndex: entry.index,
    storedHash: entry.fileSha256,
    currentHash,
    entryHash: entry.entryHash,
    recomputedHash: recomputed,
    createdAt: entry.createdAt,
  });
});

export default router;
