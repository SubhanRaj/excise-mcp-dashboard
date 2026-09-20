@props(['amount', 'default' => 'rupees'])

{{--
    Renders every unit up front and toggles which one shows with a plain Alpine
    x-show, rather than recomputing on switch — the four strings are cheap and
    this needs no JS port of Money::format().
--}}
<span x-data="{ unit: '{{ $default }}' }" {{ $attributes->merge(['class' => 'inline-flex items-center gap-1']) }}>
    @foreach(\App\Support\Money::UNITS as $unit => $divisor)
        <span x-show="unit === '{{ $unit }}'" x-cloak>{{ \App\Support\Money::format($amount, $unit) }}</span>
    @endforeach
    <select x-model="unit" aria-label="Money unit" class="text-xs border-0 bg-transparent text-slate-400 dark:text-slate-500 focus:ring-0 cursor-pointer">
        <option value="rupees">₹</option>
        <option value="thousand">K</option>
        <option value="lakh">L</option>
        <option value="crore">Cr</option>
    </select>
</span>
