import { maskAadhaar, maskPan, maskPhone, maskForAudit } from '../src/utils/contracts';

describe('Masking Utility Tests', () => {
  test('Aadhaar: 12 digit string masked correctly', () => {
    expect(maskAadhaar('498174981234')).toBe('XXXX-XXXX-1234');
  });

  test('Aadhaar: spaced format masked correctly', () => {
    expect(maskAadhaar('4981 7498 1234')).toBe('XXXX-XXXX-1234');
  });

  test('Aadhaar: invalid input returns safe placeholder', () => {
    expect(maskAadhaar('12345')).toBe('XXXX-XXXX-XXXX');
  });

  test('PAN: 10-char PAN masked correctly', () => {
    expect(maskPan('ABCDE1234F')).toBe('ABCXX1234F');
  });

  test('Phone: last 4 digits shown', () => {
    expect(maskPhone('9876543210')).toBe('XXXXXX3210');
  });

  test('maskForAudit: sanitises aadhaar field in objects', () => {
    const result = maskForAudit({ aadhaar: '498174981234', name: 'Ramesh' });
    expect(result.aadhaar).toBe('XXXX-XXXX-1234');
    expect(result.name).toBe('Ramesh'); // non-PII unchanged
  });

  test('maskForAudit: sanitises pan field', () => {
    const result = maskForAudit({ panNumber: 'ABCDE1234F' });
    expect(result.panNumber).toBe('ABCXX1234F');
  });

  test('No unmasked Aadhaar pattern in masked output', () => {
    const masked = maskAadhaar('498174981234');
    expect(masked).not.toMatch(/\d{12}/);
    expect(masked).not.toMatch(/\d{4}\s\d{4}\s\d{4}/);
  });
});
