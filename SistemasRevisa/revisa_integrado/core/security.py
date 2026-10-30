import time
from datetime import datetime

MODULE_FOLHA = "folha"
MODULE_ENERGIA = "energia"
MODULES = (MODULE_FOLHA, MODULE_ENERGIA)

# Argumentos de versões anteriores; são ignorados e nunca liberam acesso.
LEGACY_ARGUMENTS = ("--central-authenticated", "--revisa-auth-pipe", "--revisa-program", "--central-geometry")

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 30


class Session:
    """Estado de autenticação da sessão. A senha principal libera o sistema e todos os módulos.
    A senha própria do Energia e Água (acesso.json) continua valendo só para o programa autônomo."""

    def __init__(self):
        self.user = None
        self.started = None
        self._unlocked = set()

    @property
    def authenticated(self):
        return self.user is not None

    def login(self, user):
        self.user = user
        self.started = datetime.now()
        self._unlocked = set(MODULES)

    def unlock(self, module):
        if not self.authenticated:
            raise PermissionError("Entre no sistema antes de liberar módulos.")
        if module not in MODULES:
            raise ValueError(f"Módulo desconhecido: {module}")
        self._unlocked.add(module)

    def is_unlocked(self, module):
        return self.authenticated and module in self._unlocked

    def require(self, module=None):
        if not self.authenticated:
            raise PermissionError("Sessão não autenticada.")
        if module is not None and module not in self._unlocked:
            raise PermissionError(f"Acesso ao módulo '{module}' não liberado nesta sessão.")

    def logout(self):
        self.user = None
        self.started = None
        self._unlocked = set()


class AttemptLimiter:
    def __init__(self, max_attempts=MAX_ATTEMPTS, lockout_seconds=LOCKOUT_SECONDS, clock=time.monotonic):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self.clock = clock
        self.failures = 0
        self.locked_until = 0.0

    def remaining_lock(self):
        return max(0.0, self.locked_until - self.clock())

    def failure(self):
        self.failures += 1
        if self.failures >= self.max_attempts:
            self.locked_until = self.clock() + self.lockout_seconds
            self.failures = 0

    def success(self):
        self.failures = 0
        self.locked_until = 0.0


def ignored_arguments(argv):
    """Nomes dos argumentos legados recebidos (sem valores), apenas para registro."""
    found = []
    for item in argv:
        name = item.split("=", 1)[0]
        if name in LEGACY_ARGUMENTS and name not in found:
            found.append(name)
    return found


class SingleInstance:
    def __init__(self, name="Local\\SistemasRevisaIntegrado"):
        self.name = name
        self.handle = None

    def acquire(self):
        try:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (ImportError, AttributeError, OSError):
            return True
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        self.handle = kernel32.CreateMutexW(None, False, self.name)
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS

    def release(self):
        if self.handle:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
            kernel32.CloseHandle(self.handle)
            self.handle = None
