#!/usr/bin/env python3
from tkinter import *
from tkinter import font
from tkinter import messagebox
from collections import OrderedDict
from subprocess import call
from utilities import ClockMode
from threading import Timer
from enum import Enum, unique
from threading import Thread
from PIL import ImageTk
from PIL import Image
import sys
import subprocess
import random
import time
import sched
import re
import os
import usb.core
import usb.util

# Enum that declares different commands that could be sent to PICOCHESS
class PICOCHESS_COMMANDS(Enum):
    NEW_GAME_WHITE  = 1
    NEW_GAME_BLACK  = 2
    SET_GAME_LEVEL  = 3
    SET_GAME_MODE   = 4
    DECLARE_DRAW    = 5
    WHITE_RESIGNS   = 6
    BLACK_RESIGNS   = 7
    SET_ENGINE      = 8
    SEND_MOVE       = 9
    SEND_GO         = 10
    PRESS_BUTTON    = 11
# END OF PICOCHESS_COMMANDS

def find_between( s, first, last ):
    try:
        start = s.index( first ) + len( first )
        end = s.index( last, start )
        return s[start:end]
    except ValueError:
        return ""

def sendCommand2Picochess(dict):
    if 'command' not in dict:
        print ("Command not set")
        return
    command = dict['command']
    if type(command) is not PICOCHESS_COMMANDS:
        print ("Comnand is not of type PICOCHESS_COMMANDS")
        return
    strCommand = StringVar()
    if command is PICOCHESS_COMMANDS.NEW_GAME_WHITE:
        strCommand = "newgame:w"
    elif command is PICOCHESS_COMMANDS.NEW_GAME_BLACK:
        strCommand = "newgame:b"
    elif command is PICOCHESS_COMMANDS.DECLARE_DRAW:
        strCommand = "fen:8/8/8/3Kk3/8/8/8/8"
    elif command is PICOCHESS_COMMANDS.WHITE_RESIGNS:
        strCommand = "fen:8/8/8/4k3/3K4/8/8/8"
    elif command is PICOCHESS_COMMANDS.BLACK_RESIGNS:
        strCommand = "fen:8/8/8/3k4/4K3/8/8/8"
    elif command is PICOCHESS_COMMANDS.SEND_MOVE:
        strCommand = dict['move']
    elif command is PICOCHESS_COMMANDS.PRESS_BUTTON:
        strCommand = "button:" + str(dict['but_number'])
    elif command is PICOCHESS_COMMANDS.SET_GAME_MODE:
        timeMode = dict['time_mode']
        if timeMode is ClockMode.FIXED_TIME:
            strCommand = "fen:" + time_control_fixed_map[dict['game_mode_time']]
        elif timeMode is ClockMode.BLITZ:
            strCommand = "fen:" + time_control_blitz_map[dict['game_mode_time']]
        elif timeMode is ClockMode.FISCHER:
            strCommand = "fen:" + time_control_fisch_map[dict['game_mode_time']]
        else:
            print("No such time mode defined")
            return
    elif command is PICOCHESS_COMMANDS.SET_GAME_LEVEL:
        strCommand = "fen:" + level_map[dict['level']]
    elif command is PICOCHESS_COMMANDS.SET_ENGINE:
        pass
        print ('This is pass block')
    elif command is PICOCHESS_COMMANDS.SEND_GO:
        strCommand = "go"
    else:
        print ("No such command defined")
        return
    # This is the command to send input to detached screens
    # screen -S picochessScreen -p 0 -X stuff "newgame:w$(printf \\r)"
    call("screen " + "-S picochessScreen -p 0 -X stuff \"" + strCommand + "$(printf \\\r)\"",shell=True)
    if command is PICOCHESS_COMMANDS.SEND_MOVE:
        sendCommand2Picochess({'command':PICOCHESS_COMMANDS.SEND_GO})

def shutdownSystem():
    print("Shutting down the system")
    os.system('sudo shutdown -h now')

def startGame():
    print ("Starting the game with level = {}, game_mode = {} and play_as {}".format(level.get(),gameMode.get(),playAs.get()))
    # Start Picochess program on a screen session with ouput to file screenlog.0
    call("screen " + "-S picochessScreen -d -m -L ./startPicoChess.sh",shell=True)
    call("screen " + "-r picochessScreen -X logfile flush 1",shell=True) # Flush the log file every second
    print ("Wait 5 seconds to PicoChess to come up")
    time.sleep(5)
    print ("Sending game mode commands")
    sendCommand2Picochess({'command':PICOCHESS_COMMANDS.SET_GAME_LEVEL,
                          'level': level.get()})

    timeMode = ClockMode.FIXED_TIME
    if gameMode.get() == "Fixed":
        timeMode = ClockMode.FIXED_TIME
    elif gameMode.get() == "Blitz":
        timeMode = ClockMode.BLITZ
    elif gameMode.get() == "Fischer":
        timeMode = ClockMode.FISCHER

    sendCommand2Picochess({'command':PICOCHESS_COMMANDS.SET_GAME_MODE,
                          'time_mode': timeMode,
                          'game_mode_time': gameModeTime.get()})
    if playAs.get() == "White":
        sendCommand2Picochess({'command':PICOCHESS_COMMANDS.NEW_GAME_WHITE})
    else:
        sendCommand2Picochess({'command':PICOCHESS_COMMANDS.NEW_GAME_BLACK})

    clearFrame(root)
    runningGameUI(root)
    threadPicochessOutput = Thread(target=watchScreenLogFile)
    threadPicochessOutput.start()
    threadUsbBoardSensor = Thread(target=watchUsbBoard)
    threadUsbBoardSensor.start()

def convertSensorData2CheesCoordinates(data):
    # Nice tip on how to calculate log base 2 of integer:
    # http://stackoverflow.com/questions/13105875/compute-fast-log-base-2-ceiling-in-python?noredirect=1&lq=1
    if len(data) != 8:
        raise ValueError("Data array must have 8 elements")
    if data[0] != 0:
        return "a{}".format(data[0].bit_length())
    elif data[1] != 0:
        return "b{}".format(data[1].bit_length())
    elif data[2] != 0:
        return "c{}".format(data[2].bit_length())
    elif data[3] != 0:
        return "d{}".format(data[3].bit_length())
    elif data[4] != 0:
        return "e{}".format(data[4].bit_length())
    elif data[5] != 0:
        return "f{}".format(data[5].bit_length())
    elif data[6] != 0:
        return "g{}".format(data[6].bit_length())
    elif data[7] != 0:
        return "h{}".format(data[7].bit_length())
    else:
        return ""

def watchUsbBoard():
    global programRunning
    # decimal vendor and product values
    # This information should be retrieved using lsusb command
    dev = usb.core.find(idVendor=0x1941, idProduct=0x8021)
    # or, uncomment the next line to search instead by the hexidecimal equivalent
    #dev = usb.core.find(idVendor=0x45e, idProduct=0x77d)
    # first endpoint
    if dev is None:
        raise ValueError("usb board not found")
    interface = 0
    endpoint = dev[0][(0,0)][0]
    chessMove = ""
    # if the OS kernel already claimed the device, which is most likely true
    # thanks to http://stackoverflow.com/questions/8218683/pyusb-cannot-set-configuration
    if dev.is_kernel_driver_active(interface) is True:
        # tell the kernel to detach
        dev.detach_kernel_driver(interface)
        # claim the device
        usb.util.claim_interface(dev, interface)
    # As the USB chess board is a sensory one we will have to read data forever
    while programRunning:
        try:
            data = dev.read(endpoint.bEndpointAddress,endpoint.wMaxPacketSize)
            halfMove = convertSensorData2CheesCoordinates(data)
            if len(halfMove) == 0: # There is no data from the sensor
                if len(chessMove) == 4:
                    print("About to send move {} to picochess".format(chessMove))
                    sendCommand2Picochess({'command':PICOCHESS_COMMANDS.SEND_MOVE,
                          'move': chessMove})
                    chessMove = ""
            elif not chessMove.endswith(halfMove):
                print ("Half move stored {}".format(halfMove))
                chessMove = chessMove + halfMove
                print ("Chess move stored {}".format(chessMove))
                if len(chessMove) > 4:
                    print ("Stored invalid movement. Clearing it")
                    chessMove=""
        except usb.core.USBError as e:
            data = None
            if e.args == ('Operation timed out',):
                continue
    # release the device
    usb.util.release_interface(dev, interface)
    # reattach the device to the OS kernel
    dev.attach_kernel_driver(interface)


def watchScreenLogFile():
    global programRunning
    while programRunning:
        screenLog = tail( open("screenlog.0") )
        processOutput(screenLog)
    print("Exiting watchScreenLogFile")

def processOutput(output):
    global computerMove

    for line in output:
        if "Clock text:" in line:
            line = find_between(line,"Clock text:","Beep")
            line = line.strip()
            print ("Clock text is '{}'".format(line))
            if line != "okpico":
                strClock.set(line)
        elif line.startswith("Clock move:"):
            line = line.replace("Clock move:","").strip()
            print ("Computer move previous {}".format(computerMove))
            computerMove = line[:4]
            print ("Computer move {}".format(computerMove))
            # Send event to the UI
            root.event_generate("<<showComputerMoveEvent>>")
        elif line.startswith("Clock time"):
            line = line[line.find("("):line.rfind(")")+1]
            line = line.strip()
            str_clock_white = line.split('-')[0]
            str_clock_white = str_clock_white.strip()
            str_clock_white = str_clock_white.replace("(","")
            str_clock_white = str_clock_white.replace(")","")
            str_clock_white = str_clock_white.replace(" ","")
            arr_str_clock_white = str_clock_white.split(',')
            str_clock_white = "{}:{}:{}".format(arr_str_clock_white[0].zfill(2),arr_str_clock_white[1].zfill(2),arr_str_clock_white[2].zfill(2))
            str_clock_black = line.split('-')[1]
            str_clock_black = str_clock_black.strip()
            str_clock_black = str_clock_black.replace("(","")
            str_clock_black = str_clock_black.replace(")","")
            str_clock_black = str_clock_black.replace(" ","")
            arr_str_clock_black = str_clock_black.split(',')
            str_clock_black = "{}:{}:{}".format(arr_str_clock_black[0].zfill(2),arr_str_clock_black[1].zfill(2),arr_str_clock_black[2].zfill(2))
            print("About to set white clock to {} and black clock to {}".format(str_clock_white,str_clock_black))
            strClock.set(str_clock_white + "-" + str_clock_black)
            # TODO: Check for zeros on the clock so the game has finished

def showComputerMove(arg):
    strClock.set(computerMove)

def gameModeChanged(a,b,c):
    print ("Game mode has changed to {}".format(gameMode.get()))
    new_game_font = font.Font(family="Helvetica", size =20, weight="bold")
    if gameMode.get() == "Fixed":
        lbGameModeTimeStr.set("Seconds per move:")
        spGameModeTime = Spinbox(root, values=time_control_fixed_list,textvariable=gameModeTime,width=6,font=new_game_font).grid(row=2,column=1, sticky=E)
    elif gameMode.get() == "Blitz":
        lbGameModeTimeStr.set("Minutes per game:")
        spGameModeTime = Spinbox(root, values=time_control_blitz_list,textvariable=gameModeTime,width=6,font=new_game_font).grid(row=2,column=1, sticky=E)
    elif gameMode.get() == "Fischer":
        lbGameModeTimeStr.set("Mins/Secs:")
        spGameModeTime = Spinbox(root, values=time_control_fisch_list,textvariable=gameModeTime,width=6,font=new_game_font).grid(row=2,column=1, sticky=E)
    else:
        print("No such game mode expected: {}".format(gameMode.get()))

def clearFrame(frame):
    # Clear the UI
    for child in frame.winfo_children():
        child.destroy()

def cleanAppResources():
    global programRunning
    programRunning = False;
    # Kill the thread that we are using
    if threadPicochessOutput is not None:
        threadPicochessOutput.join()
    print ("All threads exited successfully")
    # Kill the screen session where PicoChess was living
    call("screen " + "-S picochessScreen -X  stuff $'\003'",shell=True)
    call("screen " + "-S picochessScreen -X  stuff $'\003'",shell=True)
    call("screen " + "-X -S picochessScreen quit",shell=True)
    # Remove the log file where the output was stored
    call("rm " + "screenlog.0",shell=True)

def endGame(dict):
    # Send appropiate commadn to Picochess
    sendCommand2Picochess(dict)
    cleanAppResources()
    clearFrame(root)
    newGameUI(root)

def runningGameUI(frame):
    # NOTE: It seems that PIL image locally created are dismissed outside the subrutine

    Label(frame,
          text="""00:00 - 00:00""",
          textvariable = strClock,
          font = bold_font,
          compound = CENTER,
          bg = "red",
          image = imgLCD).grid(row=0,column=0,columnspan=5,padx=5, pady=5)
    Button(frame,image = imgWResing , bg="red",
           command = lambda : endGame({'command':PICOCHESS_COMMANDS.WHITE_RESIGNS})).grid(row=1,column=1)
    Button(frame,image = imgDraw , bg="red",
            command = lambda : endGame({'command':PICOCHESS_COMMANDS.DECLARE_DRAW})).grid(row=1,column=2)
    Button(frame,image = imgBResing,bg="red",
            command = lambda : endGame({'command':PICOCHESS_COMMANDS.BLACK_RESIGNS})).grid(row=1,column=3)
    Button(frame,image = imgBtn1,bg="red",
            command = lambda : sendCommand2Picochess({'command':PICOCHESS_COMMANDS.PRESS_BUTTON,'but_number':0})).grid(row=2,column=0)
    Button(frame,image = imgBtn2,bg="red",
            command = lambda : sendCommand2Picochess({'command':PICOCHESS_COMMANDS.PRESS_BUTTON,'but_number':1})).grid(row=2,column=1)
    Button(frame,image = imgBtn3,bg="red",
            command = lambda : sendCommand2Picochess({'command':PICOCHESS_COMMANDS.PRESS_BUTTON,'but_number':2})).grid(row=2,column=2)
    Button(frame,image = imgBtn4,bg="red",
            command = lambda : sendCommand2Picochess({'command':PICOCHESS_COMMANDS.PRESS_BUTTON,'but_number':3})).grid(row=2,column=3)
    Button(frame,image = imgBtn5,bg="red",
            command = lambda : sendCommand2Picochess({'command':PICOCHESS_COMMANDS.PRESS_BUTTON,'but_number':4})).grid(row=2,column=4)

    frame.grid_rowconfigure(0,weight=3)
    frame.grid_rowconfigure(1,weight=1)
    frame.grid_rowconfigure(2,weight=1)
    frame.grid_columnconfigure(0,weight=1)
    frame.grid_columnconfigure(1,weight=1)
    frame.grid_columnconfigure(2,weight=1)
    frame.grid_columnconfigure(3,weight=1)
    frame.grid_columnconfigure(4,weight=1)

def newGameUI(frame):

    new_game_font = font.Font(family="Helvetica", size = 20, weight="bold")
    frame.configure(background='red')
    Label(frame,text="Level:",font = new_game_font,bg="red").grid(row=0,column=0, sticky=W)
    Spinbox(frame, values=(0,3,6,9,12,15,18,20),textvariable=level,width=3,font=new_game_font).grid(row=0,column=1, sticky=E)
    Label(frame,text="Game mode:",font=new_game_font,bg="red").grid(row=1,column=0, sticky=W)
    Spinbox(frame, values=("Fixed","Blitz","Fischer"),width=8,font=new_game_font,textvariable=gameMode).grid(row=1,column=1, sticky=E)
    # Listed for changes in this Spin Box
    gameMode.trace('w',gameModeChanged)
    lbGameModeTimeStr.set("Second per move:")
    Label(frame,font=new_game_font,bg="red",textvariable=lbGameModeTimeStr).grid(row=2,column=0, sticky=W)
    spGameModeTime = Spinbox(frame, values=time_control_fixed_list,textvariable=gameModeTime,width=6,font=new_game_font).grid(row=2,column=1, sticky=E)
    # TODO: ADD ENGINE SELECTION
    Label(root,text="Play as:",font=new_game_font,bg="red").grid(row=3,column=0, sticky=W)
    Spinbox(frame, values=("White","Black"),width=6,font=new_game_font,textvariable=playAs).grid(row=3,column=1, sticky=E)
    btStart = Button(frame,text = "Start",font=new_game_font,
                     command= startGame,bg="red").grid(row=4,column=0)
    btShutdown = Button(frame,text = "Shutdown",font=new_game_font,
                     command= shutdownSystem,bg="red").grid(row=4,column=1)
    frame.grid_rowconfigure(0,weight=1)
    frame.grid_rowconfigure(1,weight=1)
    frame.grid_rowconfigure(2,weight=1)
    frame.grid_rowconfigure(3,weight=1)
    frame.grid_rowconfigure(4,weight=2)
    frame.grid_columnconfigure(0,weight=1)
    frame.grid_columnconfigure(1,weight=1)

def key(event):
    global keysPressed

    keysPressed = keysPressed + str(event.char)
    print ("Keys pressed until now '{}'".format(keysPressed))
    if len(keysPressed) == 4:
        matchObj = re.match( r'[a-h][1-8]',keysPressed)
        if matchObj:
            sendCommand2Picochess({'command':PICOCHESS_COMMANDS.SEND_MOVE,
                          'move': keysPressed})
        keysPressed = ""


def tail(f):
    f.seek(0, 2)

    while True:
        line = f.readline()

        if not line:
            time.sleep(0.1)
            continue

        yield line

root=Tk()
# Declare global variables
threadPicochessOutput = None
threadUsbBoardSensor= None
programRunning=True
computerMove=StringVar() # Stores last computer movement
level=IntVar()
playAs=StringVar()
gameMode=StringVar()
gameModeTime=StringVar()
strClock = StringVar()
keysPressed=""
lbGameModeTimeStr=StringVar()

bold_font = font.Font(family = "Helvetica", size = 24, weight = "bold")
imgLCD = ImageTk.PhotoImage(file="res/lcd_display.png")
imgWResing = ImageTk.PhotoImage(file="res/BlackWins.png")
imgBResing = ImageTk.PhotoImage(file="res/WhiteWins.png")
imgDraw = ImageTk.PhotoImage(file="res/Draw.png")
imgBtn1 = ImageTk.PhotoImage(file="res/button1.png")
imgBtn2 = ImageTk.PhotoImage(file="res/button2.png")
imgBtn3 = ImageTk.PhotoImage(file="res/button3.png")
imgBtn4 = ImageTk.PhotoImage(file="res/button4.png")
imgBtn5 = ImageTk.PhotoImage(file="res/button5.png")

time_control_fixed_map = OrderedDict([
    ("1","rnbqkbnr/pppppppp/Q7/8/8/8/PPPPPPPP/RNBQKBNR"),
    ("3","rnbqkbnr/pppppppp/1Q6/8/8/8/PPPPPPPP/RNBQKBNR"),
    ("5","rnbqkbnr/pppppppp/2Q5/8/8/8/PPPPPPPP/RNBQKBNR"),
    ("10","rnbqkbnr/pppppppp/3Q4/8/8/8/PPPPPPPP/RNBQKBNR"),
    ("15","rnbqkbnr/pppppppp/4Q3/8/8/8/PPPPPPPP/RNBQKBNR"),
    ("30","rnbqkbnr/pppppppp/5Q2/8/8/8/PPPPPPPP/RNBQKBNR"),
    ("60","rnbqkbnr/pppppppp/6Q1/8/8/8/PPPPPPPP/RNBQKBNR"),
    ("90","rnbqkbnr/pppppppp/7Q/8/8/8/PPPPPPPP/RNBQKBNR")
    ])

time_control_blitz_map = OrderedDict([
    ("1","rnbqkbnr/pppppppp/8/8/Q7/8/PPPPPPPP/RNBQKBNR"),
    ("3","rnbqkbnr/pppppppp/8/8/1Q6/8/PPPPPPPP/RNBQKBNR"),
    ("5","rnbqkbnr/pppppppp/8/8/2Q5/8/PPPPPPPP/RNBQKBNR"),
    ("10","rnbqkbnr/pppppppp/8/8/3Q4/8/PPPPPPPP/RNBQKBNR"),
    ("15","rnbqkbnr/pppppppp/8/8/4Q3/8/PPPPPPPP/RNBQKBNR"),
    ("30","rnbqkbnr/pppppppp/8/8/5Q2/8/PPPPPPPP/RNBQKBNR"),
    ("60","rnbqkbnr/pppppppp/8/8/6Q1/8/PPPPPPPP/RNBQKBNR"),
    ("90","rnbqkbnr/pppppppp/8/8/7Q/8/PPPPPPPP/RNBQKBNR")
    ])

time_control_fisch_map = OrderedDict([
    ("1 1","rnbqkbnr/pppppppp/8/8/8/Q7/PPPPPPPP/RNBQKBNR"),
    ("3 2","rnbqkbnr/pppppppp/8/8/8/1Q6/PPPPPPPP/RNBQKBNR"),
    ("4 2","rnbqkbnr/pppppppp/8/8/8/2Q5/PPPPPPPP/RNBQKBNR"),
    ("5 3","rnbqkbnr/pppppppp/8/8/8/3Q4/PPPPPPPP/RNBQKBNR"),
    ("10 5","rnbqkbnr/pppppppp/8/8/8/4Q3/PPPPPPPP/RNBQKBNR"),
    ("15 10","rnbqkbnr/pppppppp/8/8/8/5Q2/PPPPPPPP/RNBQKBNR"),
    ("30 15","rnbqkbnr/pppppppp/8/8/8/6Q1/PPPPPPPP/RNBQKBNR"),
    ("60 30","rnbqkbnr/pppppppp/8/8/8/7Q/PPPPPPPP/RNBQKBNR")
    ])

level_map = OrderedDict([
    (0,"rnbqkbnr/pppppppp/q7/8/8/8/PPPPPPPP/RNBQKBNR"),
    (3,"rnbqkbnr/pppppppp/3q4/8/8/8/PPPPPPPP/RNBQKBNR"),
    (6,"rnbqkbnr/pppppppp/6q1/8/8/8/PPPPPPPP/RNBQKBNR"),
    (9,"rnbqkbnr/pppppppp/8/1q6/8/8/PPPPPPPP/RNBQKBNR"),
    (12,"rnbqkbnr/pppppppp/8/4q3/8/8/PPPPPPPP/RNBQKBNR"),
    (15,"rnbqkbnr/pppppppp/8/7q/8/8/PPPPPPPP/RNBQKBNR"),
    (18,"rnbqkbnr/pppppppp/8/8/2q5/8/PPPPPPPP/RNBQKBNR"),
    (20,"rnbqkbnr/pppppppp/8/8/4q3/8/PPPPPPPP/RNBQKBNR")
    ])

time_control_fixed_list = ["1", "3", "5", "10", "15", "30", "60", "90"] # Seconds per move
time_control_blitz_list = ["1", "3", "5", "10", "15", "30", "60", "90"] # Minutes per game
time_control_fisch_list = ["1  1", "3  2", "4  2", "5  3", "10  5", "15 10", "30 15", "60 30"] # Minutes / seconds of increment

# Main program
screen_width = 480
screen_height = 320
print ("Screen resolution is {}x{}".format(screen_width,screen_height))
root.geometry('{}x{}'.format(480,320))
root.resizable(width=False, height=False)
# Key bindings
root.bind("<Key>", key)
root.bind("<<showComputerMoveEvent>>", showComputerMove)
root.bind("<Escape>", lambda e: e.widget.quit())
root.title("USB Board Raspberry Pi")
root.focus_set() # <-- move focus to this widget
root.configure(background='red')
newGameUI(root)
root.attributes('-topmost', 1)
root.update()
root.attributes('-topmost', 0)
root.mainloop()
