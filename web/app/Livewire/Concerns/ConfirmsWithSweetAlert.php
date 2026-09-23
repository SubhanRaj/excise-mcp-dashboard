<?php

namespace App\Livewire\Concerns;

use Livewire\Attributes\On;

/**
 * Confirm-before-action via SweetAlert2, in place of wire:confirm's native browser dialog
 * (php-flasher/flasher-sweetalert-laravel, php-flasher.io/livewire/). A component calls
 * confirm() from its own trigger method instead of putting wire:confirm on the button; the
 * target method name and its one string argument ride through as sweetalert() options and
 * run only once SweetAlert2's own confirm button is clicked.
 *
 * The wire payload shape below (envelope.options.*) is read straight from the installed
 * package's own JS (flasher-sweetalert's renderEnvelope dispatches {promise, envelope} with
 * envelope.options carrying every option() call verbatim) and PHP (Envelope::toArray()) — not
 * from the docs, which show the pattern but not the exact wire shape.
 */
trait ConfirmsWithSweetAlert
{
    public function confirm(string $method, string $arg, string $message, string $confirmText = 'Yes'): void
    {
        // warning() must be the last call in this chain — it's the one that actually queues
        // the envelope (NotificationStorageMethods::flash() -> push()); question() only sets
        // the icon/message on the builder and, unlike the others, never pushes on its own.
        sweetalert()
            ->showDenyButton(true, 'Cancel')
            ->confirmButtonText($confirmText)
            ->option('method', $method)
            ->option('arg', $arg)
            ->warning($message);
    }

    #[On('sweetalert:confirmed')]
    public function runConfirmedAction(array $payload): void
    {
        $options = $payload['envelope']['options'] ?? [];
        $method = $options['method'] ?? null;
        $arg = $options['arg'] ?? null;

        if (is_string($method) && method_exists($this, $method)) {
            $this->{$method}($arg);
        }
    }
}
