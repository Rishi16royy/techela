"""A flask of techela."""
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import glob
import os
from pkg_resources import get_distribution
import json
import random
import shutil
import smtplib
import subprocess
import sys
import time
import urllib
import numpy as np
import matplotlib.pyplot as plt

from flask import Flask, render_template, redirect, url_for, request

__version__ = get_distribution('techela').version

app = Flask(__name__)

# We need to get this information elsewhere

print(sys.argv, len(sys.argv))
if (len(sys.argv) != 2):
    raise Exception('Did you run "python -m techela.app <course-label>"')

# I assume you run the command like "python -m techela.app <course-label>" In
# this case, -m is the first element of sys.argv, and the label is the second
# one.
COURSE = sys.argv[1]
COURSEDIR = os.path.expanduser(f'~/{COURSE}/')

# First we have get the registered course info.
COURSEINFO_URL = ('https://raw.githubusercontent.com/jkitchin/techela/'
                  f'master/registered-courses/{COURSE}.json')

try:
    local_filename, headers = urllib.request.urlretrieve(COURSEINFO_URL)
    # We succeeded in getting it, and now it is in local_filename
    # Now we make sure the COURSEDIR exists, and make it otherwise
    if not os.path.isdir(COURSEDIR):
        os.makedirs(COURSEDIR)
        os.makedirs(COURSEDIR + 'assignments/')
        os.makedirs(COURSEDIR + 'solutions/')
        os.makedirs(COURSEDIR + 'lectures/')

    if not os.path.isdir(COURSEDIR + 'graded-assignments/'):
        os.makedirs(COURSEDIR + 'graded-assignments/')

    shutil.copyfile(local_filename, COURSEDIR + 'course-data.json')

    with open(COURSEDIR + f'course-data.json') as f:
        COURSEDATA = json.loads(f.read())

except urllib.error.HTTPError:
    print('Course info not found.')
    sys.exit()

BOX_EMAIL = COURSEDATA['submit-email']
BASEURL = COURSEDATA['course-raw-url']

LECTUREURL = BASEURL + 'lectures/'
ASSIGNMENTURL = BASEURL + 'assignments/'
SOLUTIONURL = BASEURL + 'solutions/'

# This file contains user data, andrew id, name
USERCONFIG = f'{COURSEDIR}/techela.json'

# The flask app


@app.route("/coursedir")
def open_course(path=None):
    """Open the course directory in a file explorer."""
    d = COURSEDIR
    path = request.args.get('path')

    if path:
        d += path
    if sys.platform == "win32":
        os.startfile(d)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.call([opener, d])

    return redirect(url_for('hello'))


@app.route("/")
def hello():
    "This is the opening page."

    if not os.path.exists(USERCONFIG):
        return redirect(url_for('setup_view'))

    with open(USERCONFIG, encoding='utf-8') as f:
        data = json.loads(f.read())
        ANDREWID = data['ANDREWID']
        NAME = data['NAME']

    # Should be setup now. Update the course info
    ONLINE = True
    try:
        urllib.request.urlretrieve(f'{BASEURL}/course-files.json',
                                   f'{COURSEDIR}/course-files.json')
    except urllib.error.HTTPError:
        print(f'{BASEURL}/blob/master/course-files.json')
        print('Unable to download the course json file!!!!!!')
        ONLINE = False

    with open(f'{COURSEDIR}/course-files.json', encoding='utf-8') as f:
        data = json.loads(f.read())

    # First get lecture status
    lecture_paths = [os.path.join(COURSEDIR, path)
                     for path in data['lectures']]
    lecture_files = [os.path.split(path)[-1] for path in lecture_paths]

    lecture_labels = [os.path.splitext(f)[0] for f in lecture_files]

    lecture_status = ['Downloaded' if os.path.exists(path)
                      else '<font color="red">Not downloaded</font>'
                      for path in lecture_paths]

    lecture_keywords = data['lecture_keywords']

    # Next get assignments. These are in assignments/label.ipynb For students I
    # construct assignments/andrewid-label.ipynb to check if they have local
    # versions.
    assignments = data['assignments']

    assignment_files = [os.path.split(assignment)[-1]
                        for assignment in assignments]
    assignment_labels = [os.path.splitext(f)[0] for f in assignment_files]
    assignment_paths = ['{}assignments/{}-{}.ipynb'.format(COURSEDIR,
                                                           ANDREWID,
                                                           label)
                        for label in assignment_labels]
    assignment_status = ['Downloaded' if os.path.exists(path)
                         else '<font color="red">Not downloaded</font>'
                         for path in assignment_paths]

    duedates = [assignments[f]['duedate'] for f in assignments]
    colors = []
    for dd in duedates:
        today = datetime.utcnow()
        d = datetime.strptime(dd, "%Y-%m-%d %H:%M:%S")

        if (d - today).days < 0:
            colors.append('black')
        elif (d - today).days <= 2:
            colors.append('red')
        elif (d - today).days <= 7:
            colors.append('orange')
        else:
            colors.append('green')

    turned_in = []
    for path in assignment_paths:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                d = json.loads(f.read())
                ti = d['metadata'].get('TURNED-IN', None)
                if ti:
                    turned_in.append(ti['timestamp'])
                else:
                    turned_in.append('Not yet.')
        else:
            turned_in.append(None)

    solution_paths = data['solutions']
    solution_files = [os.path.split(path)[-1] for path in solution_paths]
    solution_labels = [os.path.splitext(f)[0] for f in solution_files]

    solutions = [label if label in solution_labels else None
                 for label in assignment_labels]

    # graded assignments
    graded_assignments = []
    for ipynb in glob.glob(COURSEDIR + 'graded-assignments/*.ipynb'):
        with open(ipynb, encoding='utf-8') as f:
            gd = json.loads(f.read())

            graded_assignments += [[os.path.split(ipynb)[-1],
                                    gd['metadata'].get('grade',
                                                       {}).get('overall',
                                                               None),
                                    gd['metadata']['org'].get('GRADER',
                                                              'unknown')]]

    return render_template('hello.html',
                           COURSEDATA=COURSEDATA,
                           COURSEDIR=COURSEDIR,
                           ANDREWID=ANDREWID,
                           NAME=NAME,
                           ONLINE=ONLINE,
                           announcements=data['announcements'],
                           version=__version__,
                           lectures=list(zip(lecture_labels,
                                             lecture_status,
                                             lecture_keywords)),
                           assignments4templates=list(zip(assignment_labels,
                                                          assignment_paths,
                                                          assignment_status,
                                                          colors,
                                                          duedates,
                                                          turned_in,
                                                          solutions)),
                           graded_assignments=graded_assignments)


@app.route("/debug")
def debug():
    "In debug mode this gets me to a console in the browser."
    raise(Exception)


@app.route("/about")
def about():
    import platform

    opsys = platform.platform()

    pyexe = sys.executable
    pyver = sys.version

    import techela
    techela_ver = techela.__version__

    try:
        import pycse
        pycse_ver = pycse.__version__
    except ModuleNotFoundError:
        pycse_ver = None
    return render_template('about.html',
                           **locals())


@app.route("/setup")
def setup_view():
    return render_template('setup.html')


@app.route("/setup_post", methods=['POST'])
def setup_post():
    ANDREWID = request.form['andrewid']
    NAME = request.form['fullname']

    with open(USERCONFIG, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'ANDREWID': ANDREWID.lower(),
                            'NAME': NAME}))

    return redirect(url_for('hello'))


@app.route("/lecture/<label>")
def open_lecture(label):
    fname = '{}/lectures/{}.ipynb'.format(COURSEDIR, label)
    if not os.path.exists(fname):
        urllib.request.urlretrieve(LECTUREURL
                                   + '{}.ipynb'.format(label), fname)
        # We need to check for images. Boo...
        # They look like this in the cells: ![img](./images/control-volume.png)

    # Now open the notebook.
    cmd = ["jupyter", "notebook", fname]
    subprocess.Popen(cmd, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,
                     stdin=subprocess.PIPE)

    return redirect(url_for('hello'))


@app.route("/course-lecture/<label>")
def open_course_lecture(label):
    fname = f'{COURSEDIR}/lectures/course-{label}.ipynb'

    if os.path.exists(fname):
        os.unlink(fname)
    urllib.request.urlretrieve(LECTUREURL
                               + f'{label}.ipynb',
                               fname)

    # Now open the notebook.
    cmd = ["jupyter", "notebook", fname]
    subprocess.Popen(cmd, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,
                     stdin=subprocess.PIPE)

    return redirect(url_for('hello'))


@app.route("/solution/<label>")
def open_solution(label):
    fname = f'{COURSEDIR}/solutions/{label}.ipynb'

    urllib.request.urlretrieve(SOLUTIONURL
                               + f'{label}.ipynb', fname)

    # Now open the notebook.
    cmd = ["jupyter", "notebook", fname]
    subprocess.Popen(cmd, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,
                     stdin=subprocess.PIPE)

    return redirect(url_for('hello'))


@app.route("/admin-solution/<label>")
def admin_solution(label):
    "Open admin solution"
    fname = os.path.expanduser(f"{COURSEDATA['local-box-path']}/solutions/{label}.ipynb")

    # Now open the notebook.
    cmd = ["jupyter", "notebook", fname]
    subprocess.Popen(cmd, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,
                     stdin=subprocess.PIPE)

    return redirect(url_for('admin'))


@app.route("/assignment/<label>")
def open_assignment(label):
    with open(USERCONFIG, encoding='utf-8') as f:
        data = json.loads(f.read())
        ANDREWID = data['ANDREWID']
        NAME = data['NAME']

    fname = f'{COURSEDIR}assignments/{ANDREWID}-{label}.ipynb'
    if not os.path.exists(fname):
        urllib.request.urlretrieve(f'{ASSIGNMENTURL}/{label}.ipynb',
                                   fname)

        # Insert their full name at the top
        with open(fname, encoding='utf-8') as f:
            j = json.loads(f.read())

        dt = datetime.now()

        author = {'cell_type': 'markdown',
                  'metadata': {},
                  'source': [f'{NAME} ({ANDREWID}@andrew.cmu.edu)\n',
                             'Date: {}\n'.format(dt.isoformat(" "))]}
        j['cells'].insert(0, author)

        # Also put Author metadata in so it is easy to email these back.
        j['metadata']['author'] = {}
        j['metadata']['author']['name'] = NAME
        j['metadata']['author']['email'] = f'{ANDREWID}@andrew.cmu.edu'

        with open(fname, 'w', encoding='utf-8') as f:
            f.write(json.dumps(j))

    # Now open the notebook.
    # os.system('jupyter notebook {}'.format(fname))
    cmd = ["jupyter", "notebook", fname]
    subprocess.Popen(cmd, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,
                     stdin=subprocess.PIPE)

    return redirect(url_for('hello'))


@app.route("/graded-assignment/<fname>")
def open_graded_assignment(fname):
    """Open the assignment FNAME.
    It is in the graded-assignments directory."""

    fname = COURSEDIR + f'graded-assignments/{fname}'

    cmd = ["jupyter", "notebook", fname]
    subprocess.Popen(cmd, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,
                     stdin=subprocess.PIPE)

    return redirect(url_for('hello'))


@app.route("/new")
def new_notebook():
    CWD = os.getcwd()
    os.chdir(COURSEDIR)
    cmd = ["jupyter", "notebook"]
    subprocess.Popen(cmd, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,
                     stdin=subprocess.PIPE)
    os.chdir(CWD)
    return redirect(url_for('hello'))


@app.route("/submit/<label>")
def authenticate(label):
    "Get the andrew password."
    return render_template("email.html", label=label)


@app.route("/submit_post", methods=['POST'])
def submit_post():
    """Turn in LABEL by email."""

    with open(USERCONFIG, encoding='utf-8') as f:
        data = json.loads(f.read())
        ANDREWID = data['ANDREWID']
        NAME = data['NAME']

    password = request.form['password']
    label = request.form['label']

    # Create the container (outer) email message.
    msg = MIMEMultipart()
    subject = '[{}] - Turning in {} from {}'
    msg['Subject'] = subject.format(COURSE, label, NAME)
    msg['From'] = f'{ANDREWID}@andrew.cmu.edu'
    msg['To'] = BOX_EMAIL
    msg['Cc'] = f'{ANDREWID}@andrew.cmu.edu'

    ctype = 'application/octet-stream'
    maintype, subtype = ctype.split('/', 1)

    fname = f'{COURSEDIR}/assignments/{ANDREWID}-{label}.ipynb'
    if not os.path.exists(fname):
        raise Exception(f'{fname} not found.')

    # Save some turn in data.
    with open(fname, encoding='utf-8') as f:
        j = json.loads(f.read())

    j['metadata']['TURNED-IN'] = {}
    dt = datetime.now()
    j['metadata']['TURNED-IN']['timestamp'] = dt.isoformat(" ")

    with open(fname, 'w', encoding='utf-8') as f:
        f.write(json.dumps(j))

    with open(fname, 'rb') as fp:
        attachment = MIMEBase(maintype, subtype)
        attachment.set_payload(fp.read())
        # Encode the payload using Base64
        encoders.encode_base64(attachment)
        # Set the filename parameter
        aname = f'{ANDREWID}-{label}.ipynb'
        attachment.add_header('Content-Disposition', 'attachment',
                              filename=aname)
        msg.attach(attachment)

    with smtplib.SMTP_SSL('smtp.andrew.cmu.edu', port=465) as s:
        try:
            s.login(ANDREWID, password)
        except smtplib.SMTPAuthenticationError:
            print('caught error for', label)
            # Remove turned in
            with open(fname, encoding='utf-8') as f:
                j = json.loads(f.read())
            del j['metadata']['TURNED-IN']
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(json.dumps(j))
            return render_template("password_error.html", label=label)

        s.send_message(msg)
        s.quit()

    return redirect(url_for('hello'))

# * Admin


@app.route('/admin')
def admin():
    "Setup admin page."
    # First install the new key bindings.
    import notebook.nbextensions
    from notebook.services.config import ConfigManager

    import techela
    js = f'{techela.__path__[0]}/static/techela.js'
    notebook.nbextensions.install_nbextension(js, user=True)
    cm = ConfigManager()
    cm.update('notebook', {"load_extensions": {"techela": True}})

    ONLINE = True
    try:
        urllib.request.urlretrieve(f'{BASEURL}/course-files.json',
                                   f'{COURSEDIR}/course-files.json')
    except urllib.error.HTTPError:
        print('Unable to download the course json file!!!!!!')
        ONLINE = False

    with open(USERCONFIG, encoding='utf-8') as f:
        data = json.loads(f.read())
        ANDREWID = data['ANDREWID']
        NAME = data['NAME']

    with open(f'{COURSEDIR}/course-files.json', encoding='utf-8') as f:
        data = json.loads(f.read())

    # Next get assignments. These are in assignments/label.ipynb For students I
    # construct assignments/andrewid-label.ipynb to check if they have local
    # versions.
    assignments = data['assignments']

    assignment_files = [os.path.split(assignment)[-1]
                        for assignment in assignments]
    assignment_labels = [os.path.splitext(f)[0] for f in assignment_files]
    # this is where solutions should be
    p1 = os.path.expanduser(f"{COURSEDATA['local-box-path']}/solutions/")
    solutions = [os.path.join(p1,
                              f'{label}.ipynb')
                 for label in assignment_labels]

    duedates = [assignments[f]['duedate'] for f in assignments]

    graders = [assignments[f]['grader'] for f in assignments]

    statuses = []
    for label in assignment_labels:
        p1 = os.path.expanduser(f"{COURSEDATA['local-box-path']}/assignments")
        f = os.path.join(p1,
                         label, "STATUS")

        if os.path.exists(f):
            with open(f, encoding='utf-8') as tf:
                statuses.append(tf.read())
        else:
            statuses.append(None)

    colors = []
    for status, dd in zip(statuses, duedates):
        today = datetime.utcnow()

        d = datetime.strptime(dd, "%Y-%m-%d %H:%M:%S")

        if status is not None and status.startswith('Returned'):
            colors.append('black')
        elif (d - today).days <= 2:
            colors.append('orange')
        else:
            colors.append('red')

    # Add this function so we can use it in a template
    app.jinja_env.globals.update(exists=os.path.exists)

    return render_template('admin.html',
                           COURSE=COURSE,
                           COURSEDATA=COURSEDATA,
                           NAME=NAME, ANDREWID=ANDREWID,
                           ONLINE=ONLINE,
                           assignments4templates=list(zip(assignment_labels,
                                                          duedates,
                                                          graders,
                                                          statuses,
                                                          colors,
                                                          solutions)))


def get_roster():
    """Read roster and return a list of dictionaries for each student.
The roster.csv file is just the file downloaded from s3, renamed to roster.csv.
    """
    import csv
    roster_file = os.path.expanduser(f'{COURSEDATA["local-box-path"]}/roster.csv')
    with open(roster_file, encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=',')
        rows = [row for row in reader]
        roster_entries = [dict(zip(rows[0], row)) for row in rows]
    # skip first entry that is the headers
    return roster_entries[1:]


@app.route('/course-info')
def course_info():
    "Show course info."
    return render_template('course-info.html',
                           COURSEDATA=COURSEDATA)


@app.route('/roster')
def roster():
    "Render roster page"
    with open(USERCONFIG, encoding='utf-8') as f:
        data = json.loads(f.read())
        ANDREWID = data['ANDREWID']

    admin_emails = ','.join([x + '@andrew.cmu.edu'
                             for x in COURSEDATA['admin-andrewids']])
    return render_template('roster.html',
                           admin_emails=admin_emails,
                           COURSE=COURSE,
                           ANDREWID=ANDREWID,
                           roster=get_roster())


@app.route('/grade-assignment/<label>')
def grade_assignment(label):
    """Copy assignments to the archive directory, and move them to the assignments
    directory."""

    roster = get_roster()
    # the first time you visit this page, we shuffle it, but on subsequent
    # visits we don't. The shuffle is to grade them in a different order each
    # time.
    # This is triggered by a url like /grade-assignment/label?shuffle=true
    if request.args.get('shuffle'):
        random.shuffle(roster)

    with open(f'{COURSEDIR}/course-files.json', encoding='utf-8') as f:
        data = json.loads(f.read())

    today = datetime.utcnow()
    dd = data['assignments']['assignments/{}.ipynb'.format(label)]['duedate']
    d = datetime.strptime(dd, "%Y-%m-%d %H:%M:%S")

    if (today - d).days >= 0:
        POSTDUE = True
    else:
        POSTDUE = False

    submission_dir = os.path.expanduser(f"{COURSEDATA['local-box-path']}/submissions")   # NOQA
    assignment_dir = os.path.expanduser(f"{COURSEDATA['local-box-path']}/assignments")   # NOQA
    assignment_dir = '{}/{}'.format(assignment_dir, label)

    assignment_archive_dir = os.path.expanduser(f"{COURSEDATA['local-box-path']}/"  # NOQA
                                                'assignments-archive')
    assignment_archive_dir = '{}/{}'.format(assignment_archive_dir, label)

    if not os.path.isdir(assignment_dir):
        os.makedirs(assignment_dir)

    if not os.path.isdir(assignment_archive_dir):
        os.makedirs(assignment_archive_dir)

    grade_data = []

    for entry in roster:
        andrewid = entry['Andrew ID']
        d = {}
        d['first-name'] = entry['Preferred/First Name']
        d['last-name'] = entry['Last Name']
        d['name'] = '{} {}'.format(entry['Preferred/First Name'],
                                   entry['Last Name'])

        # This is the file that was submitted
        sfile = '{}-{}.ipynb'.format(andrewid, label)
        SFILE = os.path.join(submission_dir, sfile)

        # This is an archive copy in case anything happens.
        AFILE = os.path.join(assignment_archive_dir, sfile)

        # The logic I want to happen is:
        # if we are not POSTDUE, copy it if it exists.
        # If we are POSTDUE, copy it if it does not exist in the archive.
        if ((not POSTDUE and os.path.exists(SFILE))
            or (POSTDUE and os.path.exists(SFILE)
                and not os.path.exists(AFILE))):
            shutil.copy(SFILE, AFILE)

        # Now we do the move. This is the file we will grade. We move it, so it
        # will be gone from submissions. We do not move it if it has been
        # graded.
        GFILE = os.path.join(assignment_dir, sfile)

        # We don't have the file and it is submitted we might as well collect
        # it.
        if not os.path.exists(GFILE) and os.path.exists(SFILE):
            # Now we move SFILE to GFILE
            shutil.move(SFILE, GFILE)

        # here the GFILE should exist. whether we update it depends. Let's check  # NOQA
        # if it is graded. If we have not graded it, we might as well update it.  # NOQA
        # Check for a grade and return timestamp
        # collect data in a dictionary
        d['filename'] = GFILE
        d['andrewid'] = andrewid
        d['label'] = label
        d['grade'] = None
        d['turned-in'] = None
        d['returned'] = None

        if os.path.exists(GFILE):
            with open(GFILE, encoding='utf-8') as f:
                j = json.loads(f.read())
                # if the file is ungraded, we go ahead and move it over.
                if (os.path.exists(SFILE)
                    and j['metadata'].get('grade', None) is None):
                    shutil.move(SFILE, GFILE)

                if j['metadata'].get('grade', None):
                    d['grade'] = j['metadata']['grade']['overall']
                else:
                    d['grade'] = None

                if j['metadata'].get('RETURNED', None):
                    d['returned'] = j['metadata']['RETURNED']
                else:
                    d['returned'] = None

                if j['metadata'].get("TURNED-IN"):
                    d['turned-in'] = j['metadata']['TURNED-IN']['timestamp']
                else:
                    d['turned-in'] = None

        grade_data.append(d)

    # this puts a figure inline in the page of the grade distribution.
    numeric_grades = [d['grade'] for d in grade_data if d['grade'] is not None]
    if numeric_grades:
        from io import BytesIO
        import base64
        plt.hist(numeric_grades, 20)
        plt.xlabel('Grade')
        plt.ylabel('Frequency')
        plt.xlim([0, 1])
        plt.title('Grade distribution for {}\nMean={:1.2f}'.format(label,
                                                                   np.mean(numeric_grades)))  # NOQA
        png = BytesIO()
        plt.savefig(png)
        plt.close()
        png.seek(0)
        histogram = urllib.parse.quote(base64.b64encode(png.read()))
    else:
        histogram = ""

    # Add this function so we can use it in a template
    app.jinja_env.globals.update(exists=os.path.exists)

    status_file = os.path.expanduser(f"{COURSEDATA['local-box-path']}/assignments/{label}/STATUS")   # NOQA

    # if we don't have a status file create one. If we do have one, I don't
    # think it makes sense to change it since it should either be Collected or
    # Returned.
    if not os.path.exists(status_file):
        with open(status_file, 'w', encoding='utf-8') as f:
            f.write('Collected')

    return render_template('grade-assignment.html',
                           COURSE=COURSE,
                           label=label,
                           histogram=histogram,
                           grade_data=grade_data)


@app.route('/grade/<andrewid>/<label>')
def grade(andrewid, label):
    "Opens the file for andrewid and label."
    assignment_dir = os.path.expanduser(f'{COURSEDATA["local-box-path"]}/assignments')   # NOQA
    GFILE = os.path.join(assignment_dir,
                         label,
                         f'{andrewid}-{label}.ipynb')

    with open(GFILE, encoding='utf-8') as f:
        j = json.loads(f.read())
        if j['metadata'].get('grade', None) is None:
            print('No grade in {} yet'.format(GFILE))
        else:
            tech = j['metadata']['grade']['technical']
            pres = j['metadata']['grade']['presentation']
            print('grade: ', ('technical', tech), ('presentation', pres))

    # Now open the notebook.
    cmd = ["jupyter", "notebook", GFILE]
    subprocess.Popen(cmd, stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,
                     stdin=subprocess.PIPE)

    return ('', 204)


@app.route('/open-for-grading/<label>')
def open_for_grading(label, n=5):
    "Open N ungraded LABEL assignments for grading."
    assignment_dir = os.path.expanduser(f'{COURSEDATA["local-box-path"]}/assignments') # NOQA
    # Get a list of ungraded notebooks
    all_ipynb = glob.glob(assignment_dir + '/' + label + '/*.ipynb')
    ungraded = []
    for ipynb in all_ipynb:
        with open(ipynb) as f:
            data = json.loads(f.read())
            if 'grade' not in data['metadata']:
                ungraded += [ipynb]
    random.shuffle(ungraded)
    for i in range(min(n, len(ungraded))):
        # Now open the notebooks.
        cmd = ["jupyter", "notebook", ungraded[i]]
        print( f'Running "{cmd}")')
        subprocess.Popen(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         stdin=subprocess.PIPE)
    return ('', 204)


@app.route('/return/<andrewid>/<label>')
def return_one(andrewid, label):
    """Return an assignment by email.
    If a force parameter is given return even if it was returned before.
    """
    force = True if request.args.get('force') else False

    assignment_dir = os.path.expanduser(f"{COURSEDATA['local-box-path']}/assignments")   # NOQA
    GFILE = os.path.join(assignment_dir,
                         label,
                         f'{andrewid}-{label}.ipynb')
    # Make sure file exists
    if not os.path.exists(GFILE):
        print('{} not found.'.format(GFILE))
        return redirect(url_for('grade_assignment', label=label))

    # Check for grade, we don't return ungraded files
    with open(GFILE, encoding='utf-8') as f:
        j = json.loads(f.read())
        if j['metadata'].get('grade', None) is None:
            print('No grade in {}. not returning.'.format(GFILE))
            return redirect(url_for('grade_assignment', label=label))
        tech = j['metadata']['grade']['technical']
        pres = j['metadata']['grade']['presentation']
        grade = j['metadata']['grade']['overall']
        print('grade: ', ('technical', tech), ('presentation', pres))
    # Check if it was already returned, we don't return it again unless force
    # is truthy.
    if j['metadata'].get('RETURNED', None) and not force:
        print('Returned already!')
        return redirect(url_for('grade_assignment', label=label))

    # ok, finally we have to send it back.
    EMAIL = '{}@andrew.cmu.edu'.format(andrewid)

    with open(USERCONFIG, encoding='utf-8') as f:
        data = json.loads(f.read())
        ANDREWID = data['ANDREWID']

    # Create the container (outer) email message.
    msg = MIMEMultipart()
    subject = '[{}] - {}-{}.ipynb has been graded'
    msg['Subject'] = subject.format(COURSE, andrewid, label)
    msg['From'] = '{}@andrew.cmu.edu'.format(ANDREWID)
    msg['To'] = EMAIL

    body = 'Technical: {}\nPresentation: {}\nOverall Grade = {}'.format(tech,
                                                                        pres,
                                                                        grade)

    ctype = 'application/octet-stream'
    maintype, subtype = ctype.split('/', 1)

    # Save some return data.
    with open(GFILE, encoding='utf-8') as f:
        j = json.loads(f.read())

    # Now we add the comments to the email body.
    i = 1
    comments = []
    for cell in j['cells']:
        if cell['metadata'].get('type', None) == 'comment':
            comments.append('{0}. {1}'.format(i, cell['metadata'].get('content', '')))   # NOQA
            i += 1

    if comments:
        body += '\n\nComments:\n'
        body += '\n'.join(comments)

    # Let's put a grade report in too.
    grades = get_grades(andrewid)
    # we need to delete some keys I made for convenience.
    del grades['course-overall-grade']
    del grades['name']
    del grades['first-name']
    del grades['last-name']
    # grades is a dictionary by label.

    # here we make it a list
    grades = [(k, v) for k, v in grades.items()]

    # Now we sort by the duedate. This function gets the datetime object for an
    # assignment for sorting.

    def mydate(el):
        k, v = el
        dd = v['duedate']
        d = datetime.strptime(dd, "%Y-%m-%d %H:%M:%S")
        return d

    grades = sorted(grades, key=lambda el: mydate(el), reverse=True)

    today = datetime.utcnow()
    gstring = '{0:35s} {1:15s} {2:8s} {3:10s} {4}'.format('label',
                                                          'grade',
                                                          'points',
                                                          'category',
                                                          'duedate')
    gstring += '\n' + "-" * len(gstring)

    with open(f'{COURSEDIR}/course-files.json'.format(COURSEDIR),
              encoding='utf-8') as f:
        data = json.loads(f.read())
        adata = {}
        for k, v in data['assignments'].items():
            adata[v['label']] = v

    for label, v in grades:
        p = v['path']  # path to student file
        dd = adata[label]['duedate']
        category = adata[label]['category']
        g = v.get('overall', 0.0)  # student grade
        points = str(adata[label]['points'])

        d = datetime.strptime(dd, "%Y-%m-%d %H:%M:%S")

        if (today - d).days >= 0:
            POSTDUE = True
        else:
            POSTDUE = False

        if POSTDUE and os.path.exists(p) and g is not None:
            gstring += '\n{0:35s} {1:15.3f} {4:^8s} {2:15s} {3}'.format(label, g, category, dd, points)  # NOQA
        elif POSTDUE and os.path.exists(p) and g is None:
            gstring += '\n{0:35s} {1:>15s} {4:^8s} {2:15s} {3}'.format(label,
                                                                       'not-graded', category, dd, # NOQA
                                                                       points)
        elif POSTDUE:
            gstring += '\n{0:35s} {1:>15s} {4:^8s} {2:15s} {3}'.format(label,
                                                                       'missing', category,   # NOQA
                                                                       dd,
                                                                       points)

    body += '\n\nGrades\n======\n'
    body += gstring

    dt = datetime.now()
    j['metadata']['RETURNED'] = dt.isoformat(" ")

    with open(GFILE, 'w', encoding='utf-8') as f:
        f.write(json.dumps(j))

    with open(GFILE, 'rb') as fp:
        attachment = MIMEBase(maintype, subtype)
        attachment.set_payload(fp.read())
        # Encode the payload using Base64
        encoders.encode_base64(attachment)
        # Set the filename parameter
        attachment.add_header('Content-Disposition', 'attachment',
                              filename=os.path.split(GFILE)[-1])
        msg.attach(attachment)

    msg.attach(MIMEText(body, 'plain'))

    print(msg)

    with smtplib.SMTP_SSL('relay.andrew.cmu.edu', port=465) as s:
        s.send_message(msg)
        s.quit()

    return ('', 204)


@app.route('/return-all/<label>')
def return_all(label):
    """Return all the assignments for label."""

    roster = get_roster()
    andrewids = [d['Andrew ID'] for d in roster]

    for andrewid in andrewids:
        return_one(andrewid, label)
        time.sleep(1)

    status_file = os.path.join(os.path.expanduser(f"{COURSEDATA['local-box-path']}/assignments/"),   # NOQA
                               label, "STATUS")

    with open(status_file, 'w', encoding='utf-8') as f:
        f.write('Returned')

    return redirect(url_for('grade_assignment', label=label))


def get_grades(andrewid):
    """Return a dictionary of grades for andrewid."""
    with open(f'{COURSEDIR}/course-files.json', encoding='utf-8') as f:
        data = json.loads(f.read())

    # Next get assignments. These are in assignments/label.ipynb For students I
    # construct assignments/andrewid-label.ipynb to check if they have local
    # versions.
    assignments = data['assignments']

    assignment_paths = assignments.keys()

    assignment_files = [os.path.split(path)[-1]
                        for path in assignment_paths]

    assignment_labels = [os.path.splitext(f)[0] for f in assignment_files]

    assignment_dir = os.path.expanduser(f"{COURSEDATA['local-box-path']}/assignments")   # NOQA

    duedates = [assignments[path]['duedate'] for path in assignment_paths]

    grades = {}

    for label, dd in zip(assignment_labels, duedates):
        today = datetime.utcnow()
        d = datetime.strptime(dd, "%Y-%m-%d %H:%M:%S")

        # We only look at assignments that are post due
        if (today - d).days >= 0:
            # the student file
            sfile = '{assignment_dir}/{label}/{andrewid}-{label}.ipynb'.format(**locals())

            if os.path.exists(sfile):
                with open(sfile, encoding='utf-8') as f:
                    j = json.loads(f.read())
                    if j['metadata'].get('grade', None):
                        grades[label] = {'andrewid': andrewid,
                                         'path': sfile,
                                         'technical': j['metadata']['grade']['technical'],
                                         'presentation': j['metadata']['grade']['presentation'],
                                         'overall': j['metadata']['grade']['overall'],
                                         'category': assignments['assignments/{}.ipynb'.format(label)]['category'],
                                         'points': assignments['assignments/{}.ipynb'.format(label)]['points'],
                                         'duedate': assignments['assignments/{}.ipynb'.format(label)]['duedate']}
            else:
                grades[label] = {'andrewid': andrewid,
                                 'technical': None,
                                 'presentation': None,
                                 'overall': None,
                                 'category': assignments['assignments/{}.ipynb'.format(label)]['category'],
                                 'points': assignments['assignments/{}.ipynb'.format(label)]['points'],
                                 'duedate': assignments['assignments/{}.ipynb'.format(label)]['duedate'],
                                 'path': sfile}

    # add name
    roster = get_roster()
    for d in roster:
        if andrewid == d['Andrew ID']:
            grades['first-name'] = d['Preferred/First Name']
            grades['last-name'] = d['Last Name']
            grades['name'] = '{} {}'.format(d['Preferred/First Name'],
                                            d['Last Name'])
            break

    # Compute overall grade
    # these are the categories and weights
    categories = dict(list(zip(*COURSEDATA['categories'])))
    # categories = {'homework': 0.15,
    #               'exam1': 0.2,
    #               'exam2': 0.3,
    #               'final': 0.35}

    overall_possible_points = 0
    overall_earned_points = 0
    for key in grades:
        if key not in assignment_labels:
            continue
        cat = grades[key]['category']

        possible_points = int(grades[key].get('points', 0) or 0)
        overall_grade = float(grades[key]['overall'] or 0.0)

        overall_earned_points += overall_grade * possible_points * categories[cat]
        overall_possible_points += possible_points * categories[cat]
        # GRADED = False
        # f = os.path.join(os.path.expanduser(f"{COURSEDATA['local-box-path']}/assignments"),
        #                  key, "STATUS")
        # if os.path.exists(f):
        #     with open(f, encoding='utf-8') as tf:
        #         status = tf.read()
        #             print(status)
        #             if status == 'Returned':
        #                 GRADED = True
        #     print(f, os.path.exists(f), 'PD', POSTDUE, 'GRaded: ', GRADED)
        #     if POSTDUE and GRADED:
        #         possible_points = int(grades[key].get('points', 0) or 0)
        #         overall_grade = float(grades[key]['overall'] or 0.0)

        #         overall_earned_points += overall_grade * possible_points * categories[cat]
        #         overall_possible_points += possible_points * categories[cat]

    grades['course-overall-grade'] = overall_earned_points / overall_possible_points
    return grades


@app.route('/gradebook_one/<andrewid>')
def gradebook_one(andrewid):
    """Gather grades for andrewid."""

    grades = get_grades(andrewid)
    with open('{}/course-files.json'.format(COURSEDIR), encoding='utf-8') as f:
        data = json.loads(f.read())

    # Next get assignments. These are in assignments/label.ipynb For students I
    # construct assignments/andrewid-label.ipynb to check if they have local
    # versions.
    assignments = data['assignments']

    assignment_files = [os.path.split(assignment)[-1]
                        for assignment in assignments]
    assignment_labels = [os.path.splitext(f)[0] for f in assignment_files]

    return render_template('gradebook_one.html',
                           COURSE=COURSE,
                           name=grades['name'],
                           andrewid=andrewid,
                           course_overall_grade=round(grades['course-overall-grade'], 3),
                           assignment_labels=assignment_labels,
                           grades=grades)

@app.route('/gradebook')
def gradebook():

    with open('{}/course-files.json'.format(COURSEDIR), encoding='utf-8') as f:
        data = json.loads(f.read())

    # Next get assignments. These are in assignments/label.ipynb For students I
    # construct assignments/andrewid-label.ipynb to check if they have local
    # versions.
    assignments = data['assignments']

    assignment_files = [os.path.split(assignment)[-1]
                        for assignment in assignments]
    assignment_labels = [os.path.splitext(f)[0] for f in assignment_files]


    headings = ['First name',
                'Last name',
                'Andrew ID',
                'Overall']

    # Add each assignment label
    headings += assignment_labels

    roster = get_roster()

    ROWS = []
    for d in roster:
        ROW = []
        ROW += [d['Preferred/First Name'],
                d['Last Name'],
                d['Andrew ID']]

        grades = get_grades(d['Andrew ID'])
        ROW += [round(grades['course-overall-grade'], 3)]

        for label in assignment_labels:
            asn = grades.get(label, None)
            if asn:
                if asn['overall'] is not None:
                    ROW += [round(asn['overall'], 2)]
                else:
                    ROW += [None]
            else:
                ROW += [None]

        ROWS += [ROW]

    app.jinja_env.globals.update(isinstance=isinstance,
                                 float=float)
    return render_template('gradebook.html',
                           headings=headings,
                           ROWS=ROWS)
