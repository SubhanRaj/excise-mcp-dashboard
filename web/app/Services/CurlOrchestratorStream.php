<?php

namespace App\Services;

/**
 * Streams a POST to the orchestrator and yields each ndjson line, decoded, as it
 * actually arrives. Guzzle's own `stream => true` was the original implementation here
 * — every handler it has (curl, PHP's stream wrapper, with or without Laravel's own HTTP
 * client wrapping it) turned out to buffer the whole response and only release it once
 * the orchestrator's connection closed, confirmed directly against this box: a plain
 * `curl` CLI call to the same endpoint streamed normally, every PHP variant did not.
 * `CURLOPT_WRITEFUNCTION`, polled through `curl_multi_exec`, is the one mechanism here
 * that delivers each chunk as it lands on the socket — the same thing the curl binary
 * itself uses.
 */
class CurlOrchestratorStream implements OrchestratorStream
{
    public function stream(string $path, array $payload, callable $isTimedOut): \Generator
    {
        $url = rtrim(config('services.orchestrator.base_url'), '/').$path;
        $token = config('services.orchestrator.token');

        $queued = [];
        $buffer = '';
        $start = microtime(true);
        $lastDataAt = $start;

        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => json_encode($payload, JSON_THROW_ON_ERROR),
            CURLOPT_HTTPHEADER => ["Authorization: Bearer {$token}", 'Content-Type: application/json'],
            CURLOPT_TIMEOUT => 0,
            CURLOPT_WRITEFUNCTION => function ($ch, string $data) use (&$buffer, &$queued, &$lastDataAt) {
                $lastDataAt = microtime(true);
                $buffer .= $data;
                while (($newlineAt = strpos($buffer, "\n")) !== false) {
                    $line = trim(substr($buffer, 0, $newlineAt));
                    $buffer = substr($buffer, $newlineAt + 1);
                    if ($line !== '') {
                        $queued[] = json_decode($line, true, 512, JSON_THROW_ON_ERROR);
                    }
                }

                return strlen($data);
            },
        ]);

        $mh = curl_multi_init();
        curl_multi_add_handle($mh, $ch);
        $running = null;

        try {
            do {
                curl_multi_exec($mh, $running);
                while ($queued) {
                    yield array_shift($queued);
                }
                if ($running) {
                    if ($isTimedOut(microtime(true) - $lastDataAt, microtime(true) - $start)) {
                        throw new \RuntimeException("orchestrator {$path}: stream timed out");
                    }
                    curl_multi_select($mh, 1.0);
                }
            } while ($running);

            $error = curl_error($ch);
            $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
            if ($error !== '') {
                throw new \RuntimeException("orchestrator {$path}: {$error}");
            }
            if ($httpCode >= 400) {
                $detail = trim($buffer) !== '' ? ' — '.trim($buffer) : '';
                throw new \RuntimeException("orchestrator {$path}: HTTP {$httpCode}{$detail}");
            }
        } finally {
            curl_multi_remove_handle($mh, $ch);
            curl_close($ch);
            curl_multi_close($mh);
        }
    }
}
