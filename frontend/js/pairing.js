/**
 * Pure auto-pairing function for bulk book cover uploads.
 */

export function parseFileName(filename) {
  const noExt = filename.replace(/\.[^/.]+$/, '').trim();

  // Front: _front, -front, front, _cover, -cover, cover, or with separator _f, -f, _1, -1
  const frontRegex = /^(.*?)(?:[_\-\s]?(?:front|cover)|[_\-\s]+(?:f|1))$/i;
  // Back: _back, -back, back, _rear, -rear, rear, or with separator _b, -b, _2, -2
  const backRegex = /^(.*?)(?:[_\-\s]?(?:back|rear)|[_\-\s]+(?:b|2))$/i;

  const frontMatch = noExt.match(frontRegex);
  if (frontMatch) {
    const base = frontMatch[1].replace(/[_\-\s]+$/, '') || 'Book';
    return { base: base.toLowerCase(), displayBase: base, side: 'front' };
  }

  const backMatch = noExt.match(backRegex);
  if (backMatch) {
    const base = backMatch[1].replace(/[_\-\s]+$/, '') || 'Book';
    return { base: base.toLowerCase(), displayBase: base, side: 'back' };
  }

  return { base: noExt.toLowerCase(), displayBase: noExt, side: null };
}

export function pairFiles(fileList) {
  if (!fileList || !fileList.length) {
    return { pairs: [], unpaired: [], pairedByOrder: false };
  }

  const parsed = Array.from(fileList).map((file, idx) => {
    const name = file.name || `file_${idx}`;
    const { base, displayBase, side } = parseFileName(name);
    const label = displayBase.replace(/[_\-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || `Book ${idx + 1}`;
    return {
      id: `file_${idx}_${Math.random().toString(36).slice(2, 7)}`,
      file,
      name,
      base,
      displayLabel: label,
      side,
      index: idx,
    };
  });

  // Attempt pattern-based grouping by common base
  const groups = new Map();
  const unmatched = [];

  parsed.forEach(item => {
    if (item.side) {
      if (!groups.has(item.base)) {
        groups.set(item.base, { label: item.displayLabel, front: null, back: null });
      }
      const g = groups.get(item.base);
      if (item.side === 'front' && !g.front) {
        g.front = item;
      } else if (item.side === 'back' && !g.back) {
        g.back = item;
      } else {
        unmatched.push(item);
      }
    } else {
      unmatched.push(item);
    }
  });

  const matchedPairs = [];
  groups.forEach((g) => {
    if (g.front && g.back) {
      matchedPairs.push({
        id: `book_${matchedPairs.length + 1}_${Math.random().toString(36).slice(2, 7)}`,
        label: g.label,
        front: g.front,
        back: g.back,
      });
    } else if (g.front) {
      matchedPairs.push({
        id: `book_${matchedPairs.length + 1}_${Math.random().toString(36).slice(2, 7)}`,
        label: g.label,
        front: g.front,
        back: null,
      });
    } else if (g.back) {
      unmatched.push(g.back);
    }
  });

  // If pattern matching found at least one pair with front+back, use name matching
  const hasMatchedTwoSides = matchedPairs.some(p => p.front && p.back);
  if (hasMatchedTwoSides) {
    return { pairs: matchedPairs, unpaired: unmatched, pairedByOrder: false };
  }

  // Fallback: Pair by upload order
  const pairs = [];
  const orderUnpaired = [];
  for (let i = 0; i < parsed.length; i += 2) {
    if (i + 1 < parsed.length) {
      pairs.push({
        id: `book_${pairs.length + 1}_${Math.random().toString(36).slice(2, 7)}`,
        label: `Book ${pairs.length + 1}`,
        front: parsed[i],
        back: parsed[i + 1],
      });
    } else {
      orderUnpaired.push(parsed[i]);
    }
  }

  return { pairs, unpaired: orderUnpaired, pairedByOrder: true };
}
