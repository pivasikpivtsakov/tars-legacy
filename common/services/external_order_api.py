from logging import getLogger

import httpx
from fastapi import status

from common.environment import API_TIMEOUT, API_TOKEN, API_URL, APP_ENVIRONMENT
from common.exceptions.orders import OrderProcessingError
from common.models.orders import ExternalOrderStatus as Status
from common.schemas.external_order import ExternalOrder
from common.services.request_service import MethodsEnum, RequestService

CONTROLLER_RETRY_DELAY = 60
PATH_CODE_EXCHANGE_TIME = "/activators/code_exchange_time"
PATH_CODE_EXCHANGE_STATUS = "/activators/code_exchange_status"
PATH_CODES_GET = "/codes/get"
PATH_CODES_REPLACE = "/codes/replace"
PATH_CODES_SET_STATUS = "/codes/set_status"
PATH_ORDERS_SET_STATUS = "/orders/set_status"
PATH_ORDER_COMPLETE = "/orders/complete"
PATH_ORDER_UPDATE_CODES = "/orders/update_codes_info"
PATH_ORDER_GET = "/orders/get"
PATH_SEND_MSG_TO_MODERATORS = "/telegram/send_message_to_moderators"


logger = getLogger(__name__)


class ExternalOrderApi:
    def __init__(
        self,
        *,
        requests: RequestService,
    ) -> None:
        self._requests = requests

    async def get_order(self, order: ExternalOrder) -> ExternalOrder | None:
        url = f"{API_URL}{PATH_ORDER_GET}"
        r = await self._requests.request(
            method=MethodsEnum.GET,
            url=url,
            authorization_token=API_TOKEN,
            timeout=API_TIMEOUT,
            params={
                "order_id": order.original_id,
            },
        )
        if not r or r.status_code == status.HTTP_403_FORBIDDEN:
            msg = (
                f"❌ <b>Не удалось получить данные по заказу: {order.original_id}"
                "</b>\n Ошибка ответа контроллера.\nУдаляем заказ"
            )
            logger.exception(r.text if r else "Response text not found")
            raise OrderProcessingError(msg)
        if r.status_code != status.HTTP_200_OK or (r.json() is None):
            msg = (
                f"❌ <b>Не удалось получить данные по заказу: {order.original_id}"
                "</b>\n Заказ не найден в контроллере.\nУдаляем заказ"
            )
            logger.exception(r.text if r else "Response text not found")
            raise OrderProcessingError(msg)
        if r.json().get("status") not in (Status.FAILED, Status.PENDING):
            msg = (
                f"❌ <b>Ошибка статуса заказа: {order.original_id} "
                "в контроллере </b>\n Заказ не в статусе FAILED, PENDING."
                "\nУдаляем заказ"
            )
            logger.exception(r.text if r.text else "Response text not found")
            raise OrderProcessingError(msg)
        res = r.json()
        order.shop_access_key = res.get("shop_access_key")
        order.amount = res.get("amount")
        order.pubg_id = res.get("pubg_id")
        order.status = res.get("status")
        order.status_reason = res.get("status_reason")
        order.codes = res.get("codes")
        order.broken_codes = res.get("broken_codes")
        order.redeemed_codes = res.get("redeemed_codes")
        order.additional_data = res.get("additional_data")

        # was missing in original code, added by Mikhail, uncomment later
        # order.unused_codes = res.get("unused_codes")

        return order

    async def check_order_finished(
        self,
        order: ExternalOrder,
        user_id: int,
        is_w_codes: bool,
    ) -> tuple[bool, bool, list[str]]:
        """Check codes whether codes activated correctly

        Returns:
            tuple[bool, bool, list[str]]: first value whether order is finished,
            the second whether fraud is found in order,
            and the third the codes whose activation could not be verified (assumed activated)
        """
        if is_w_codes is False:
            return True, False, []
        if APP_ENVIRONMENT == "local":
            return True, False, []
        pubg_id = str(order.additional_data.get("player_open_id"))
        unverified_codes: list[str] = []
        for code in order.unused_codes:
            res = await self.get_code_exchange_time(
                code=code,
                order=order,
            )
            if not res or res.status_code != status.HTTP_200_OK:
                order.additional_data.setdefault("debug_messages", []).append(
                    f"Не удалось проверить активацию кода: {code}, считаем, что активирован"
                )
                unverified_codes.append(code)
                continue
            res = res.json()
            if res.get("is_redeemed") is False:
                msg = (
                    f"Заказ: {order.original_id} Код: {code} не активирован,"
                    f" Юзер id:{user_id} получит сообщение"
                    " о необходимости активации"
                )
                order.additional_data.setdefault("debug_messages", []).append(msg)
                logger.info(msg)
                return False, False, unverified_codes
            if pubg_id is not None and str(pubg_id) != str(res.get("exchange_open_id")):
                order.additional_data.setdefault("debug_messages", []).append(
                    f"Код: {code} активирован на отличный id,"
                    f" {pubg_id} != {res.get('exchange_open_id')}"
                    f" Юзер id:{user_id} будет заблокирован"
                )
                return False, True, unverified_codes
        return True, False, unverified_codes

    async def change_order_status(self, order: ExternalOrder) -> None:
        if APP_ENVIRONMENT == "local":
            return
        url = f"{API_URL}{PATH_ORDERS_SET_STATUS}"
        r = await self._requests.request(
            method=MethodsEnum.PATCH,
            url=url,
            authorization_token=order.shop_access_key,
            timeout=API_TIMEOUT,
            params={
                "order_id": order.original_id,
                "new_status": Status.MANUAL_PROCESSING,
            },
        )
        if r and r.status_code == status.HTTP_200_OK and r.json().get("success") is True:
            return
        logger.exception(r.text if r else "Response text not found")
        if r.status_code == status.HTTP_200_OK and r.json().get("success") is False:
            msg = (
                f"❌ <b>Не удалось сменить статус заказу: {order.original_id}"
                " на MANUAL_PROCESSING.</b> Удаляем заказ"
            )
        elif r.status_code == status.HTTP_400_BAD_REQUEST:
            msg = f"❌ <b>Не удалось найти заказ: {order.original_id}</b>Удаляем заказ"
        else:
            msg = (
                "❌ <b>Ошибка контроллера при попытке сменить статус заказу:"
                f" {order.original_id}</b> Удаляем заказ"
            )
        logger.exception(msg)
        raise OrderProcessingError(msg)

    async def check_unused_codes(self, order: ExternalOrder) -> tuple[ExternalOrder, list[str]]:
        if APP_ENVIRONMENT == "local":
            return order, []
        codes_to_add = {}
        codes_to_remove = []
        msg_to_admins = []
        for code, amount in order.unused_codes.items():
            await self._check_unused_code(
                code=code,
                amount=amount,
                order=order,
                codes_to_add=codes_to_add,
                codes_to_remove=codes_to_remove,
                messages_to_admin=msg_to_admins,
            )
        for code in codes_to_remove:
            if code in order.unused_codes:
                order.unused_codes.pop(code)
        order.unused_codes.update(codes_to_add)
        return order, msg_to_admins

    async def _check_unused_code(
        self,
        code: str,
        amount: int,
        order: ExternalOrder,
        codes_to_add: dict[str, int],
        codes_to_remove: list[str],
        messages_to_admin: list[str],
    ) -> None:
        player_open_id = str(order.additional_data.get("player_open_id"))
        if res := await self.get_code_exchange_time(code=code, order=order):
            if not res:
                return
            if str(res.status_code).startswith("5"):
                order.additional_data.setdefault(519553468, []).append(
                    f"Не удалось проверить код: {code}, считаем, что корректный"
                )
                return
            if res.status_code == status.HTTP_400_BAD_REQUEST:
                order.redeemed_codes.append(code)
                codes_to_remove.append(code)
                order.additional_data.setdefault("debug_messages", []).append(
                    f"Получено 400 при проверке кода: {code},"
                    "считаем, что уже использован. Меняем статус на "
                    f"redeemed within {order.original_id}"
                )
                await self.send_change_codes_status(
                    codes=[code],
                    status=f"redeemed within {order.original_id}",
                    order=order,
                )
                return
            if res.status_code == status.HTTP_200_OK:
                await self._handle_check_code_response(
                    res=res.json(),
                    code=code,
                    amount=amount,
                    player_open_id=player_open_id,
                    order=order,
                    codes_to_add=codes_to_add,
                    codes_to_remove=codes_to_remove,
                    messages_to_admin=messages_to_admin,
                )

    async def _handle_check_code_response(
        self,
        res: dict,
        code: str,
        amount: int,
        player_open_id: str,
        order: ExternalOrder,
        codes_to_add: dict[str, int],
        codes_to_remove: list[str],
        messages_to_admin: list[str],
    ) -> None:
        if res.get("is_redeemed") is True:
            msg = f"Code already redeemed: {code}"
            logger.info(msg)
            exchange_open_id = str(res.get("exchange_open_id"))
            if player_open_id and exchange_open_id and (exchange_open_id == player_open_id):
                order.redeemed_codes.append(code)
                codes_to_remove.append(code)
                order.additional_data.setdefault("debug_messages", []).append(
                    f"Найден корректно активированный код: {code},"
                    "Меняем статус на "
                    f"redeemed within {order.original_id}"
                )
                await self.send_change_codes_status(
                    codes=[code],
                    status=f"redeemed within {order.original_id}",
                    order=order,
                )
                messages_to_admin.append(
                    f"🙆‍♂️ <b>Найден корректно активированный ранее код: {code}"
                    f" в заказе: {order.original_id}</b>"
                )
                return
            if player_open_id and exchange_open_id:
                order.broken_codes.append(code)
                codes_to_remove.append(code)
                msg = (
                    f"Заказ: {order.original_id}\n"
                    f"Найден активированный код: {code} на другой"
                    f" player_open_id: {player_open_id} != "
                    f"{exchange_open_id}, Меняем статус на "
                    f"broken within {order.original_id}"
                )
                order.additional_data.setdefault("debug_messages", []).append(msg)
                msg = (
                    f"⚠️ <b>Сломанные коды в заказе: {order.original_id}</b>:\n"
                    f"Найден активированный код: {code} на другой"
                    f" player_open_id: {player_open_id} != {exchange_open_id}\n"
                    f"Меняем статус на broken within {order.original_id}"
                )
                messages_to_admin.append(msg)
                await self.send_change_codes_status(
                    codes=[code],
                    status=f"broken within {order.original_id}",
                    order=order,
                )
                if new_code := await self.replace_code(
                    code=code,
                    amount=amount,
                    code_status=f"broken within {order.original_id}",
                    order=order,
                ):
                    codes_to_add[new_code] = amount
                    await self.send_change_codes_status(
                        codes=[new_code],
                        status=f"reedeming within {order.id}",
                        order=order,
                    )
                    msg = (
                        f"Заказ: {order.original_id}\n успешно поменяли"
                        f" код: {code} на код: {new_code}"
                    )
                    order.additional_data.setdefault("debug_messages", []).append(msg)
                    msg = (
                        f"🖊 <b>В заказе {order.original_id} успешно поменяли"
                        f" код: {code} на {new_code}</b>"
                    )
                    messages_to_admin.append(msg)
                    return
                msg = (
                    f"Заказ: {order.original_id}\n Не удалось"
                    f" заменить код: {code} для заказа"
                    f" {order.original_id}, пропускаем"
                )
                order.additional_data.setdefault("debug_messages", []).append(msg)
                logger.exception(msg)
                msg = (
                    f"✖️ <b>Не удалось заменить код: {code} для заказа:"
                    f" {order.original_id}</b>\n"
                    "Пропускаем"
                )
                messages_to_admin.append(msg)
                return
        elif res.get("amount") and amount != res.get("amount"):
            order.broken_codes.append(code)
            codes_to_remove.append(code)
            msg = (
                f"Заказ: {order.original_id}\n"
                f"Найден код: {code} с некорректной стоимостью"
                f" {amount} != {res.get('amount')}\n"
                "Меняем статус на available"
            )
            order.additional_data.setdefault("debug_messages", []).append(msg)
            msg = (
                f"⚠️ <b>Сломанные коды в заказе: {order.original_id}</b>:\n"
                f"Найден код: {code} с некорректной стоимостью"
                f" {amount} != {res.get('amount')}\n"
                "Меняем статус на available"
            )
            messages_to_admin.append(msg)
            await self.send_change_codes_status(codes=[code], status="available", order=order)
            if new_code := await self.get_code(amount=amount, order=order):
                codes_to_add[new_code] = res.get("amount")
                await self.send_change_codes_status(
                    codes=[new_code],
                    status=f"reedeming within {order.id}",
                    order=order,
                )
                msg = f"Успешно поменяли код: {code} на код: {new_code}"
                order.additional_data.setdefault("debug_messages", []).append(msg)
                return
            msg = f"Заказ: {order.original_id}\nНе удалось заменить код: {code}, пропускаем"
            order.additional_data.setdefault("debug_messages", []).append(msg)
            logger.exception(msg)
            msg = (
                f"✖️ <b>Не удалось заменить код: {code} для заказа:"
                f" {order.original_id}</b>\n"
                "Пропускаем"
            )
            messages_to_admin.append(msg)
            return

    async def get_code_exchange_status(
        self,
        code: str,
        order: ExternalOrder,
    ) -> httpx.Response | None:
        url = f"{API_URL}{PATH_CODE_EXCHANGE_STATUS}"
        return await self._requests.request(
            method=MethodsEnum.GET,
            url=url,
            timeout=API_TIMEOUT,
            authorization_token=order.shop_access_key,
            params={
                "code": code,
            },
        )

    async def get_code_exchange_time(
        self, code: str, order: ExternalOrder
    ) -> httpx.Response | None:
        url = f"{API_URL}{PATH_CODE_EXCHANGE_TIME}"
        return await self._requests.request(
            method=MethodsEnum.GET,
            url=url,
            timeout=API_TIMEOUT,
            authorization_token=order.shop_access_key,
            params={
                "code": code,
            },
        )

    async def send_change_codes_status(
        self, codes: list[str], status: str, order: ExternalOrder
    ) -> None:
        if APP_ENVIRONMENT == "local":
            return
        url = f"{API_URL}{PATH_CODES_SET_STATUS}"
        await self._requests.request(
            method=MethodsEnum.PATCH,
            url=url,
            timeout=API_TIMEOUT,
            authorization_token=order.shop_access_key,
            data={"codes": codes, "status": status},
        )

    async def replace_code(
        self, code: str, amount: int, code_status: str, order: ExternalOrder
    ) -> str | None:
        url = f"{API_URL}{PATH_CODES_REPLACE}"
        r = await self._requests.request(
            method=MethodsEnum.POST,
            url=url,
            timeout=API_TIMEOUT,
            authorization_token=order.shop_access_key,
            data={
                "replacing_code": code,
                "replacing_code_amount": amount,
                "replacing_code_status": code_status,
                "new_code_status": f"reedeming within {order.id}",
            },
        )
        if r.status_code == status.HTTP_200_OK and r.json().get("code"):
            return r.json().get("code")
        return None

    async def get_code(
        self,
        amount: int,
        order: ExternalOrder,
    ) -> str | None:
        url = f"{API_URL}{PATH_CODES_GET}"
        r = await self._requests.request(
            method=MethodsEnum.GET,
            url=url,
            timeout=API_TIMEOUT,
            authorization_token=order.shop_access_key,
            params={
                "amounts": [amount],
                "number_of_codes": 1,
                "status": "available",
                "new_code_status": f"redeeming within {order.original_id}",
            },
        )
        if r.status_code == status.HTTP_200_OK and len(r.json()) > 0:
            return r.json()[0].get("code")
        return None

    async def send_complete_order(self, order: ExternalOrder, is_w_codes: bool) -> None:
        if APP_ENVIRONMENT == "local":
            return
        url = f"{API_URL}{PATH_ORDER_COMPLETE}"
        r = await self._requests.request(
            method=MethodsEnum.PATCH,
            url=url,
            timeout=API_TIMEOUT,
            authorization_token=order.shop_access_key,
            params={"order_id": order.original_id, "with_codes": is_w_codes},
        )
        if not r or r.status_code != status.HTTP_200_OK:
            msg = f"Wrong response for request: {r.text if r else ''}"
            logger.exception(msg)

    async def send_update_codes(self, order: ExternalOrder) -> None:
        if APP_ENVIRONMENT == "local":
            return
        url = f"{API_URL}{PATH_ORDER_UPDATE_CODES}"
        r = await self._requests.request(
            method=MethodsEnum.PUT,
            url=url,
            timeout=API_TIMEOUT,
            authorization_token=order.shop_access_key,
            params={
                "order_id": order.original_id,
            },
            data={
                "unused_codes": order.unused_codes,
                "broken_codes": order.broken_codes,
                "redeemed_codes": order.redeemed_codes,
                "additional_data": order.additional_data,
            },
        )
        if not r or r.status_code != status.HTTP_200_OK:
            msg = f"Wrong response for request: {r.text if r else ''}"
            logger.exception(msg)

    async def return_codes(self, order: ExternalOrder) -> ExternalOrder:
        if APP_ENVIRONMENT == "local":
            return order
        await self.send_change_codes_status(
            codes=list(order.unused_codes.keys()), status="available", order=order
        )
        order.unused_codes = {}
        msg = "Заказ выполнен без кодов, возвращаем коды"
        order.additional_data.setdefault("debug_messages", []).append(msg)
        return order
