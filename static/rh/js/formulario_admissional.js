(function () {
    const rules = {
        cpf: { exact: 11, message: 'O CPF deve conter exatamente 11 dígitos.' },
        pis: { exact: 11, message: 'O PIS deve conter exatamente 11 dígitos.' },
        cep: { exact: 8, message: 'O CEP deve conter exatamente 8 dígitos.' },
        numero_ctps: { max: 11, optional: true, message: 'O número da CTPS deve conter no máximo 11 dígitos.' },
        serie_ctps: { exact: 4, optional: true, message: 'A série da CTPS deve conter exatamente 4 dígitos.' },
        numero_rg: { max: 9, message: 'O RG deve conter no máximo 9 dígitos.' },
        titulo_eleitor: { max: 12, optional: true, message: 'O título de eleitor deve conter no máximo 12 dígitos.' },
        numero_cnh: { exact: 9, optional: true, message: 'A CNH deve conter exatamente 9 dígitos.' }
    };

    function fieldName(input) {
        return (input.name || '').split('-').pop();
    }

    function normalizedPhone(value) {
        return (value || '').replace(/\D/g, '');
    }

    function setFeedback(input, message) {
        let feedback = input.parentElement.querySelector('.invalid-feedback[data-inline-feedback="true"]');
        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            feedback.dataset.inlineFeedback = 'true';
            input.insertAdjacentElement('afterend', feedback);
        }
        feedback.textContent = message || '';
        feedback.style.display = message ? 'block' : 'none';
        input.classList.toggle('is-invalid', Boolean(message));
        input.classList.toggle('is-valid', !message && Boolean(input.value));
    }

    function validateDigits(input) {
        const rule = rules[fieldName(input)];
        if (!rule) return true;

        const value = input.value.replace(/\D/g, '');
        input.value = value;

        let message = '';
        if (!(rule.optional && value.length === 0)) {
            if (rule.exact && value.length !== rule.exact) message = rule.message;
            if (rule.max && value.length > rule.max) message = rule.message;
        }
        setFeedback(input, message);
        return !message;
    }

    function validatePhones() {
        const principal = document.querySelector('[name="telefone_principal"]');
        const recado = document.querySelector('[name="contato_recado"]');
        if (!principal || !recado) return true;

        const principalDigits = normalizedPhone(principal.value);
        const recadoDigits = normalizedPhone(recado.value);
        if (principalDigits && recadoDigits && principalDigits === recadoDigits) {
            setFeedback(recado, 'O telefone para recado não pode ser igual ao telefone principal.');
            return false;
        }
        if (recado.classList.contains('is-invalid')) {
            const feedback = recado.parentElement.querySelector('.invalid-feedback[data-inline-feedback="true"]');
            if (feedback && feedback.textContent === 'O telefone para recado não pode ser igual ao telefone principal.') {
                setFeedback(recado, '');
            }
        }
        return true;
    }

    function bindOnlyDigits(context) {
        (context || document).querySelectorAll('[data-only-digits="true"]').forEach(function (input) {
            if (input.dataset.onlyDigitsBound === 'true') return;
            input.dataset.onlyDigitsBound = 'true';
            input.addEventListener('input', function () {
                const maxLength = parseInt(input.getAttribute('maxlength') || '0', 10);
                let value = input.value.replace(/\D/g, '');
                if (maxLength > 0) value = value.slice(0, maxLength);
                input.value = value;
            });
            input.addEventListener('blur', function () { validateDigits(input); });
        });
    }

    function bindPhones() {
        document.querySelectorAll('[name="telefone_principal"], [name="contato_recado"]').forEach(function (input) {
            if (input.dataset.phoneBlurBound === 'true') return;
            input.dataset.phoneBlurBound = 'true';
            input.addEventListener('blur', validatePhones);
        });
    }

    function applyForeignBirthState() {
        const estadoNascimento = document.querySelector('[name="estado_nascimento"]');
        const naturalidade = document.querySelector('[name="naturalidade"]');
        if (!estadoNascimento || !naturalidade) return;

        if (!naturalidade.dataset.originalOptions) {
            naturalidade.dataset.originalOptions = naturalidade.innerHTML;
        }

        if (estadoNascimento.value === 'EX') {
            naturalidade.innerHTML = '<option value="ESTRANGEIRO" selected>ESTRANGEIRO</option>';
            naturalidade.value = 'ESTRANGEIRO';
            return;
        }

        if (naturalidade.innerHTML !== naturalidade.dataset.originalOptions) {
            naturalidade.innerHTML = naturalidade.dataset.originalOptions;
            if (naturalidade.value === 'ESTRANGEIRO') {
                naturalidade.value = '';
            }
        }
    }

    function bindBirthState() {
        const estadoNascimento = document.querySelector('[name="estado_nascimento"]');
        if (!estadoNascimento || estadoNascimento.dataset.birthStateBound === 'true') return;
        estadoNascimento.dataset.birthStateBound = 'true';
        estadoNascimento.addEventListener('change', applyForeignBirthState);
        applyForeignBirthState();
    }

    window.inicializarFormularioAdmissional = function (context) {
        bindOnlyDigits(context || document);
        bindPhones();
        bindBirthState();
    };

    document.addEventListener('DOMContentLoaded', function () {
        window.inicializarFormularioAdmissional(document);
    });
}());
