import { numericTransformer } from './numeric.transformer';

describe('numericTransformer', () => {
  describe('from (database -> entity)', () => {
    it('converts the string node-postgres returns for numeric into a number', () => {
      // The actual defect: GET /users/:id served ieltsScore as "7.5", so the
      // profile page's ieltsScore.toFixed(1) threw "toFixed is not a function".
      expect(numericTransformer.from('7.5')).toBe(7.5);
      expect(typeof numericTransformer.from('7.5')).toBe('number');
    });

    it('preserves the fixed-scale values these columns actually hold', () => {
      expect(numericTransformer.from('3.85')).toBe(3.85);
      expect(numericTransformer.from('9.0')).toBe(9);
      expect(numericTransformer.from('0.0')).toBe(0);
    });

    it('keeps a NULL column null rather than coercing it to 0', () => {
      // 0 is a real IELTS band and a real GPA. Turning "not provided" into 0
      // would make an empty profile look complete and would be scored.
      expect(numericTransformer.from(null)).toBeNull();
      expect(numericTransformer.from(undefined)).toBeNull();
    });

    it('returns null rather than NaN for an unparseable value', () => {
      // NaN propagates silently through arithmetic and comparisons; null is
      // handled explicitly by every consumer of these fields.
      expect(numericTransformer.from('not-a-number')).toBeNull();
    });

    it('is idempotent if handed a value that is already a number', () => {
      expect(numericTransformer.from(7.5 as unknown as string)).toBe(7.5);
    });
  });

  describe('to (entity -> database)', () => {
    it('writes numbers through unchanged', () => {
      expect(numericTransformer.to(7.5)).toBe(7.5);
      expect(numericTransformer.to(0)).toBe(0);
    });

    it('normalises undefined to null so an unset field clears the column', () => {
      expect(numericTransformer.to(null)).toBeNull();
      expect(numericTransformer.to(undefined)).toBeNull();
    });
  });
});
