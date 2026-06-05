from wisper.injector import TextInjector


class FakeController:
    def __init__(self):
        self.typed = ""

    def type(self, text):
        self.typed += text


def test_type_passes_text_to_controller():
    fake = FakeController()
    inj = TextInjector(controller=fake)
    inj.type("ça a été élevé")
    assert fake.typed == "ça a été élevé"


def test_type_empty_string_is_noop():
    fake = FakeController()
    inj = TextInjector(controller=fake)
    inj.type("")
    assert fake.typed == ""
