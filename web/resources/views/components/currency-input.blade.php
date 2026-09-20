@props([
    'id',
    'name' => null,
    'wireModel' => null,
    'value' => null,
    'placeholder' => '0.00',
])

{{--
    Ported from excise-budget-tracker's currency-input component. Two inputs: a
    visible one Cleave.js formats for display (Indian lakh/crore digit grouping
    as the user types), and a hidden one holding the raw numeric value — the one
    actually bound to Livewire (wireModel) or submitted with a plain form (name).
    wire:ignore keeps Livewire's own re-render from fighting Cleave's DOM writes
    on the visible input; only meaningful inside a Livewire component, harmless
    elsewhere.
--}}
<div wire:ignore>
    <input type="text" inputmode="decimal" id="{{ $id }}-display" placeholder="{{ $placeholder }}"
           value="{{ $value !== null && $value !== '' ? number_format((float) $value, 2) : '' }}"
           {{ $attributes->merge(['class' => 'field-input']) }}>
</div>
@if($wireModel)
<input type="hidden" id="{{ $id }}-raw" wire:model.live.debounce.500ms="{{ $wireModel }}">
@else
<input type="hidden" id="{{ $id }}-raw" name="{{ $name }}" value="{{ $value }}">
@endif

@once
<script src="https://cdn.jsdelivr.net/npm/cleave.js@1.6.0/dist/cleave.min.js"></script>
@endonce

@if($wireModel)
@script
<script>
    new Cleave(document.getElementById('{{ $id }}-display'), {
        numeral: true,
        numeralThousandsGroupStyle: 'lakh',
        numeralDecimalScale: 2,
        numeralPositiveOnly: true,
        onValueChanged: (e) => {
            const raw = document.getElementById('{{ $id }}-raw');
            raw.value = e.target.rawValue;
            raw.dispatchEvent(new Event('input', { bubbles: true }));
        },
    });
</script>
@endscript
@else
@push('scripts')
<script>
document.addEventListener('livewire:navigated', function initCurrencyInput() {
    const display = document.getElementById('{{ $id }}-display');
    if (!display || display.dataset.cleaveInit) {
        return;
    }
    display.dataset.cleaveInit = '1';
    new Cleave(display, {
        numeral: true,
        numeralThousandsGroupStyle: 'lakh',
        numeralDecimalScale: 2,
        numeralPositiveOnly: true,
        onValueChanged: (e) => {
            document.getElementById('{{ $id }}-raw').value = e.target.rawValue;
        },
    });
});
</script>
@endpush
@endif
