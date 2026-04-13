"""
Mock gRPC server implementing envoy.service.auth.v3.Authorization/Check.

Uses only grpcio (no codegen). Protobuf encoding is done manually so the
container only needs: pip install grpcio
"""
from concurrent import futures
import grpc
import traceback


# ---------------------------------------------------------------------------
# Minimal protobuf helpers
# ---------------------------------------------------------------------------

def _varint(n):
    result = []
    while True:
        bits = n & 0x7f
        n >>= 7
        if n:
            result.append(bits | 0x80)
        else:
            result.append(bits)
            break
    return bytes(result)

def _field_string(field_num, s):
    encoded = s.encode("utf-8")
    return _varint((field_num << 3) | 2) + _varint(len(encoded)) + encoded

def _field_message(field_num, msg_bytes):
    return _varint((field_num << 3) | 2) + _varint(len(msg_bytes)) + msg_bytes

def _read_varint(data, i):
    result = shift = 0
    while True:
        b = data[i]; i += 1
        result |= (b & 0x7f) << shift
        shift += 7
        if not (b & 0x80):
            return result, i

def _parse_fields(data):
    """Parse protobuf binary into {field_num: bytes}. Values are always bytes."""
    fields = {}
    i = 0
    while i < len(data):
        tag, i = _read_varint(data, i)
        field_num = tag >> 3
        wire_type = tag & 0x7
        if wire_type == 2:              # length-delimited (string / bytes / message)
            length, i = _read_varint(data, i)
            fields[field_num] = data[i:i + length]
            i += length
        elif wire_type == 0:            # varint — skip
            _, i = _read_varint(data, i)
        elif wire_type == 1:            # 64-bit fixed — skip
            i += 8
        elif wire_type == 5:            # 32-bit fixed — skip
            i += 4
        else:
            break
    return fields

def _str(fields, field_num, default="?"):
    return fields.get(field_num, default.encode()).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Build a CheckResponse protobuf
# CheckResponse { status: Status { code: 0, message: "..." } }
# ---------------------------------------------------------------------------

def build_check_response(message):
    # Status: field 2 = message string (code 0 is default, omitted)
    status_bytes = _field_string(2, message)
    # CheckResponse: field 1 = Status
    return _field_message(1, status_bytes)


# ---------------------------------------------------------------------------
# gRPC handler
# ---------------------------------------------------------------------------

class AuthorizationHandler(grpc.GenericRpcHandler):

    def service(self, handler_call_details=None):
        # grpcio 1.80+ calls service(handler_call_details) for dispatch
        if handler_call_details is None:
            return None
        print(f"[MOCK-GRPC] service dispatch: {handler_call_details.method}", flush=True)
        if handler_call_details.method.endswith("/Check"):
            return grpc.unary_unary_rpc_method_handler(
                self._check,
                request_deserializer=lambda b: b,
                response_serializer=lambda b: b,
            )
        return None

    # kept for grpcio < 1.80 compatibility
    def service_rpc_handler(self, handler_call_details):
        return self.service(handler_call_details)

    def _check(self, request_bytes, context):
        import sys, traceback as tb
        try:
            print(f"[MOCK-GRPC] Check called, request size={len(request_bytes)}", flush=True)
            msg = "OK - mock gateway-auth-service"
            response = build_check_response(msg)
            print(f"[MOCK-GRPC] Returning response, size={len(response)}", flush=True)
            return response
        except Exception:
            tb.print_exc(file=sys.stdout)
            sys.stdout.flush()
            raise


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
server.add_generic_rpc_handlers([AuthorizationHandler()])
server.add_insecure_port("[::]:3000")
server.start()
print("[MOCK-GRPC] Listening on port 3000")
server.wait_for_termination()
