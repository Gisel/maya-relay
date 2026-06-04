from app.db import SupabaseRelayRepository


class Response:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, table, name):
        self.table = table
        self.name = name

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def insert(self, payload):
        self.table.inserted_payload = payload
        return self

    def execute(self):
        if self.table.inserted_payload is not None:
            if self.name == "contacts":
                payload = {
                    "id": "contact-1",
                    "display_name": None,
                    "lookup_name": None,
                    **self.table.inserted_payload,
                }
            else:
                payload = {
                    "id": "conversation-1",
                    "created_at": "2026-06-04T00:00:00Z",
                    **self.table.inserted_payload,
                }
            return Response([payload])
        return Response([])


class Table:
    def __init__(self, name):
        self.name = name
        self.inserted_payload = None

    def query(self):
        return Query(self, self.name)


class Client:
    def __init__(self):
        self.tables = {"conversations": Table("conversations"), "contacts": Table("contacts")}

    def table(self, name):
        return self.tables[name].query()


def test_get_or_create_customer_conversation_uses_supported_insert_shape():
    client = Client()
    repository = SupabaseRelayRepository(client)

    conversation = repository.get_or_create_customer_conversation(
        customer_phone="+15550000001",
        assigned_employee="+15551234567",
    )

    assert conversation.id == "conversation-1"
    assert conversation.customer_phone == "+15550000001"
    assert conversation.assigned_employee == "+15551234567"
    assert conversation.status == "open"
