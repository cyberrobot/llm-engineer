import os

from locust import FastHttpUser, between, task


class PublicChatUser(FastHttpUser):
    wait_time = between(0.05, 0.2)

    @task
    def public_chat(self) -> None:
        scenario = os.getenv("LOAD_SCENARIO", "baseline")
        headers = {
            "Content-Type": "application/json",
            "Origin": "http://localhost:5173",
        }
        if scenario == "oversized":
            with self.client.post(
                "/public/assistants/redmoor/chat",
                data='{"message":"' + "x" * 40_000 + '"}',
                headers=headers,
                name="oversized",
                catch_response=True,
            ) as response:
                if response.status_code != 413:
                    response.failure(f"expected 413, received {response.status_code}")
                else:
                    response.success()
            return

        with self.client.post(
            "/public/assistants/redmoor/chat",
            json={"message": "What services are available?"},
            headers=headers,
            name=scenario,
            stream=scenario == "disconnect",
            catch_response=True,
        ) as response:
            if scenario == "disconnect":
                if response._response is not None:
                    response._response.release()
                response.success()
                return
            if response.status_code == 200:
                if "event: complete" not in response.text and "event: error" not in response.text:
                    response.failure("stream had no terminal event")
            elif response.status_code in {429, 503}:
                response.success()
            else:
                response.failure(f"unexpected status {response.status_code}")
