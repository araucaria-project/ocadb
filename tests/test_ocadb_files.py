import pytest
from ocadb.models import Object


def test_canonized_name():
    assert Object.name_canonizator("Hello World!") == "helloworld"
    assert Object.name_canonizator("123 ABC!") == "123abc"
    assert Object.name_canonizator("Test@123") == "test123"
    assert Object.name_canonizator("NoChange") == "nochange"
    assert Object.name_canonizator("With Spaces ") == "withspaces"
    assert Object.name_canonizator("With - Dashes") == "withdashes"
    assert Object.name_canonizator("With_underscores") == "withunderscores"
    assert Object.name_canonizator("tz-for") == "tzfor"