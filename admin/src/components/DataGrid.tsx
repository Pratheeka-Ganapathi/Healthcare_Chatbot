import type { Cell, TablePage } from "../api/types";

function CellValue({ value }: { value: Cell }) {
  if (value === null) return <span className="null">null</span>;
  const text = String(value);
  return <span title={text}>{text}</span>;
}

/** Read-only rows of one database table. Long values are cut short; the title holds the rest. */
export function DataGrid({ page }: { page: TablePage }) {
  if (page.rows.length === 0) return <p className="empty">This table has no rows.</p>;
  return (
    <div className="table-wrap">
      <table className="data grid">
        <thead>
          <tr>
            {page.columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {page.rows.map((row, rowIndex) => (
            <tr key={page.offset + rowIndex}>
              {row.map((value, columnIndex) => (
                <td key={columnIndex} className={typeof value === "number" ? "num" : undefined}>
                  <CellValue value={value} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
