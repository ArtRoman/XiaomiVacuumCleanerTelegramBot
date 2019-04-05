import logging
from functools import wraps
from typing import List, Dict

from telegram import Bot, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ConversationHandler, Updater, CommandHandler, RegexHandler

from xml_parser import XMLParser
from xvc_helper import XVCHelper, XVCHelperBase
from xvc_util import Rectangle


# constants
MAIN_BUTTONS = ['Status', 'Home', 'ZoneCleaning']
FAN_BUTTONS = [value.name for value in XVCHelper.FanLevel]

MAIN_MENU, SELECT_FAN, SELECT_ZONE = range(3)

LIST_OF_ADMINS = [110086856, 829623593]

# logging
logging.basicConfig(format='%(asctime)s - %(levelname)6s - %(message)s', level=logging.INFO)


# functions
def build_menu(buttons, columns=2, header_buttons=None, footer_buttons=None):
    """
    Creates a telegram menu with buttons.

    :param buttons: List of buttons.
    :param columns: Number of columns
    :param header_buttons: Special header buttons.
    :param footer_buttons: Special footer buttons.
    :return: List of buttons.
    """
    menu = [buttons[i:i + columns] for i in range(0, len(buttons), columns)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


def restricted(func):
    """
    Decorator to restrict access of bot.

    :param func: Function reference.
    :return: Wrapper function.
    """
    @wraps(func)
    def wrapped(self, bot: Bot, update: Update, *args: List, **kwargs: Dict):
        user_id = update.effective_user.id
        if user_id not in LIST_OF_ADMINS:
            update.message.reply_text('Access denied for you ({})!'.format(user_id))
            return
        return func(self, bot, update, *args, **kwargs)
    return wrapped


# classes
class XVCBot(object):

    def __init__(self, vacuum: XVCHelperBase, zones: Dict[str, List[Rectangle]]):
        """
        Initializes the Xiaomi Vacuum Cleaner Bot.
        This bot is used as an conversation bot with various states.

        :param vacuum: Reference to vacuum cleaner.
        :param zones: Dictionary with all cleaning zones.
        """
        self.__vacuum = vacuum
        self.__zones = zones
        self.__main_buttons = ReplyKeyboardMarkup(build_menu(MAIN_BUTTONS),
                                                  one_time_keyboard=True)
        self.__fan_buttons = ReplyKeyboardMarkup(build_menu(FAN_BUTTONS),
                                                 one_time_keyboard=True)
        self.__zone_buttons = ReplyKeyboardMarkup(build_menu([zone.title() for zone in self.__zones.keys()]),
                                                  one_time_keyboard=True)

    def __finish(self, update: Update, message: str) -> int:
        """
        Helper function to finish the conversation.

        :param update: Bot update.
        :param message: Message to send.
        :return: State for conversation end.
        """
        update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    @restricted
    def start(self, _: Bot, update: Update) -> int:
        """
        Starts the conversation with the main menu.

        :param _: Unused parameter.
        :param update: Bot update.
        :return: State for main menu.
        """
        update.message.reply_text('Main menu', reply_markup=self.__main_buttons)
        return MAIN_MENU

    def status(self, _: Bot, update: Update) -> int:
        """
        Reads the current status of the vacuum cleaner.

        :param _: Unused parameter.
        :param update: Bot update.
        :return: State for conversation end.
        """
        result, state = self.__vacuum.status()
        if result:
            message = 'State: {}'.format(state)
        else:
            message = 'Error'
        return self.__finish(update, message)

    def home(self, _: Bot, update: Update) -> int:
        """
        Stops cleaning and sends vacuum cleaner back to the dock.

        :param _: Unused parameter.
        :param update:  Bot update.
        :return: State for conversation end.
        """
        if self.__vacuum.home():
            message = 'Vacuum cleaner goes back to the dock...'
        else:
            message = 'Error'
        return self.__finish(update, message)

    def select_fan(self, _: Bot, update: Update) -> int:
        """
        Creates the menu for fan speed.

        :param _: Unused parameter.
        :param update: Bot update.
        :return: State for selecting fan speed.
        """
        update.message.reply_text('Select fan speed!', reply_markup=self.__fan_buttons)
        return SELECT_FAN

    def select_zone(self, _: Bot, update: Update) -> int:
        """
        Creates the menu for cleaning zones.

        :param _: Unused parameter.
        :param update: Bot update.
        :return: State for selecting cleaning zone.
        """
        level = update.message.text
        self.__vacuum.set_fan_level(XVCHelperBase.FanLevel[level])
        update.message.reply_text('Select zone!', reply_markup=self.__zone_buttons)
        return SELECT_ZONE

    def cleaning(self, _: Bot, update: Update) -> int:
        """
        Starts cleaning.

        :param _: Unused parameter.
        :param update: Bot update.
        :return: State for conversation end.
        """
        zone = update.message.text
        if self.__vacuum.start_zone_cleaning(self.__zones[zone.upper()]):
            message = 'Start cleaning {}...'.format(zone)
        else:
            message = 'Error'
        return self.__finish(update, message)

    def cancel(self, _: Bot, update: Update) -> int:
        """
        Cancels the current conversation.

        :param _: Unused parameter.
        :param update: Bot update.
        :return: State for conversation end.
        """
        message = 'Canceled...'
        return self.__finish(update, message)

    def error(self, _: Bot, update: Update, message: str) -> None:
        """
        Helper function to handle any runtime errors.

        :param _: Unused parameter.
        :param update: Bot update.
        :param message: Error message.
        """
        update.message.reply_text('Update "{}" caused error "{}"!'.format(update, message),
                                  reply_markup=self.__main_buttons)


def main():

    # configuration
    xml_parser = XMLParser('config.xml')
    config_bot = xml_parser.parse_telegram_bot()

    config_xiaomi = xml_parser.parse_xiaomi_vacuum_cleaner_settings()
    vacuum = XVCHelper(config_xiaomi.ip_address, config_xiaomi.token)

    zones = xml_parser.parse_zones()

    xvc_bot = XVCBot(vacuum, zones)

    updater = Updater(token=config_bot.token)
    dispatcher = updater.dispatcher

    conversation_handler = ConversationHandler(
            entry_points=[CommandHandler('start', xvc_bot.start)],
            states={
                MAIN_MENU: [RegexHandler('^({})$'.format('Status'),
                                         xvc_bot.status),
                            RegexHandler('^({})$'.format('Home'),
                                         xvc_bot.home),
                            RegexHandler('^({})$'.format('ZoneCleaning'),
                                         xvc_bot.select_fan)],
                SELECT_FAN: [RegexHandler('^({})$'.format('|'.join(FAN_BUTTONS)),
                                          xvc_bot.select_zone)],
                SELECT_ZONE: [RegexHandler('^({})$'.format('|'.join([zone.title() for zone in zones.keys()])),
                                           xvc_bot.cleaning)]
            },
            fallbacks=[CommandHandler('cancel', xvc_bot.cancel)]
    )

    dispatcher.add_handler(conversation_handler)
    dispatcher.add_error_handler(xvc_bot.error)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
