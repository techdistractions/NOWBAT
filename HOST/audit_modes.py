"""Shared operator-mode contract for the host stream and audit runner."""
NATIVE_MODES = ('FULL', 'WIN101', 'WIN200', 'WIN300', 'STARTSHOT',
                'GUISYNC', 'MOUSE', 'WINDOW', 'INPUT', 'KEYBOARD')
OPERATOR_MODES = NATIVE_MODES + ('INPUTABI','REGRESSION')
