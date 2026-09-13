<?php

namespace App\Services;

use OpenSpout\Common\Entity\Row;
use OpenSpout\Writer\XLSX\Writer as XlsxWriter;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\HttpFoundation\StreamedResponse;

/**
 * Turns a header row + data rows into a downloadable file. CSV/XLSX only — the fleet's
 * PDF/SQL export formats aren't part of this app's Ask/Chat result export
 * (ROADMAP.md Milestone 5's Chart canvas bullet).
 */
class ExportService
{
    public const FORMATS = ['csv', 'xlsx'];

    /**
     * @param  list<string>  $columns
     * @param  list<array<int, scalar|null>>  $rows
     */
    public function download(string $format, string $filename, array $columns, array $rows): Response
    {
        return match ($format) {
            'csv' => $this->csv($filename, $columns, $rows),
            'xlsx' => $this->xlsx($filename, $columns, $rows),
            default => abort(422, "Unsupported export format: {$format}"),
        };
    }

    private function csv(string $filename, array $columns, array $rows): StreamedResponse
    {
        return response()->streamDownload(function () use ($columns, $rows) {
            $out = fopen('php://output', 'w');
            fputcsv($out, $columns);
            foreach ($rows as $row) {
                fputcsv($out, $row);
            }
            fclose($out);
        }, "{$filename}.csv", ['Content-Type' => 'text/csv']);
    }

    private function xlsx(string $filename, array $columns, array $rows): Response
    {
        $tmp = tempnam(sys_get_temp_dir(), 'export').'.xlsx';

        $writer = new XlsxWriter;
        $writer->openToFile($tmp);
        $writer->addRow(Row::fromValues($columns));
        foreach ($rows as $row) {
            $writer->addRow(Row::fromValues($row));
        }
        $writer->close();

        return response()->download($tmp, "{$filename}.xlsx")->deleteFileAfterSend();
    }
}
