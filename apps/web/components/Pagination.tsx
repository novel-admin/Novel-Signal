"use client";

type PaginationProps = { hasNext: boolean; hasPrevious?: boolean; onNext: () => void; onPrevious?: () => void; total?: number };

export function Pagination({ hasNext, hasPrevious = false, onNext, onPrevious, total }: PaginationProps) {
  return <nav className="pagination" aria-label="Pagination">
    {onPrevious && <button type="button" className="button" disabled={!hasPrevious} onClick={onPrevious}>Previous</button>}
    {total !== undefined && <span className="muted">{total} records</span>}
    <button type="button" className="button" disabled={!hasNext} onClick={onNext}>Next</button>
  </nav>;
}
