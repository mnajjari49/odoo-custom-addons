# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
CT = fields.Datetime.context_timestamp
from odoo.exceptions import UserError
import datetime
from datetime import timedelta, date
from pytz import timezone, all_timezones, UTC
import time


def period_datetime(a, b):
    dt_list = []
    nod = (b - a).days
    if a.date() == b.date():
        return [[a, b]]
    dt_list.append([a, a.replace(hour=23, minute=59, second=59, microsecond=999999)])
    for i in range(1 , nod):
        dt_list.append([a.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=i),
                    a.replace(hour=23, minute=59, second=59, microsecond=999999)+ datetime.timedelta(days=i)])
    dt_list.append([b.replace(hour=0, minute=0, second=0, microsecond=0), b])
    return dt_list


class resource_calendar(models.Model):
    _inherit = "resource.calendar"

    overtime_off_days = fields.Float('Holiday Overtime Rate')
    overtime_work_days = fields.Float('Normal Overtime Rate')


class hr_overtime(models.Model):
    _name = "hr.overtime"
    _rec_name = "employee_id"
    _order = "id desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    employee_id = fields.Many2one('hr.employee', 'Employee', required=True, readonly=True, states={'draft': [('readonly', False)]}, track_visibility='onchange')
    date = fields.Date('Date', required=True, readonly=True, default=fields.Date.today(), states={'draft': [('readonly', False)]}, track_visibility='onchange')
    start_datetime = fields.Datetime('Start Date', required=True, readonly=True, states={'draft': [('readonly', False)]}, track_visibility='onchange')
    end_datetime = fields.Datetime('End Date', required=True, readonly=True, states={'draft': [('readonly', False)]}, track_visibility='onchange')
    start_datetime_text = fields.Char('Employee Start Date',   compute='_compute_text_field', store=True)
    end_datetime_text = fields.Char('Employee End Date', compute='_compute_text_field', store=True)
    duration = fields.Float('Duration by hour', compute='calculate_overtime', readonly=True, store=True)
    overtime = fields.Float('Overtime by hour', compute='calculate_overtime', readonly=True, store=True)
    analytic_account_id = fields.Many2one('account.analytic.account',string="Cost Center/Project", readonly=True, states={'draft': [('readonly', False)]}, track_visibility='onchange')
    state = fields.Selection([('draft', 'Draft'),
                              ('confirmed', 'Confirmed'),
                              ('first_approve', 'First Approval'),
                              ('second_approve', 'Second Approval'),
                              ('done', 'Done'),
                              ('cancel', 'Canceled')], string='Status', default='draft', track_visibility='onchange')
    cost = fields.Float('Total Cost', compute='calculate_overtime', readonly=True, store=True)
    analytic_line_id = fields.Many2one('account.analytic.line', readonly=True,copy=False, track_visibility='onchange')
    payslip_id = fields.Many2one('hr.payslip', 'Payslip', readonly=True)
    show_analytic_fields = fields.Boolean(compute='_compute_show_analytic_fields')
    is_employee = fields.Boolean(compute='_compute_is_employee')
    do_first_approval = fields.Boolean(compute='button_privilege')
    do_second_approval = fields.Boolean(compute='button_privilege')
    do_done = fields.Boolean(compute='button_privilege')
    note = fields.Text('Notes')
     #custom categories overtime
    
    tang_ca_ngay_le = fields.Float('Overtime on holiday', compute='get_hour')
    tang_ca_ngay_le22 = fields.Float('Overtime on holiday after 22h', compute='get_hour')
    tang_ca_ngay_cuoi_tuan = fields.Float('Overtime on weekend day', compute='get_hour')
    tang_ca_ngay_cuoi_tuan22 = fields.Float('Overtime on weekend day after 22h', compute='get_hour')
    tang_ca_ngay_thuong = fields.Float('Overtime on normal day', compute='get_hour')
    tang_ca_ngay_thuong22 = fields.Float('Overtime on normal day after 22h', compute='get_hour')
    # cost_after22 = fields.Float('Cost before 22h', compute='calculate_overtime', readonly=True, store=True)
    global_leave = []
    working_time = []
    anchor_time = [
        {'anchor': 22,'bonus': 0},
        {'anchor': 24,'bonus': 0.5}
    ]
    bonus_by_daytype = {
        'normal_day' : {
        "0": 0.5, # Mon
        "1": 0.5, # Tue
        "2": 0.5, # Wed
        "3": 0.5, # Thu
        "4": 0.5, # Fri
        "5": 2.0, # Sat
        "6": 2.0 # Sun
        },
        'global_leave':{
        "0": 3.0, # Mon
        "1": 3.0,# Tue
        "2": 3.0, # Wed
        "3": 3.0, # Thu
        "4": 3.0, # Fri
        "5": 3.0, #Sat
        "6": 3.0 # Sun
        }
    }
    @api.depends('end_datetime','start_datetime','employee_id')
    def _compute_text_field(self):
        record_lang = self.env['res.lang'].search([("code", "=", self._context['lang'])], limit=1)
        format_date, format_time = record_lang.date_format,record_lang.time_format
        strftime_pattern = (u"%s %s" % (format_date,format_time))
        for rec in self:
            if rec.end_datetime and rec.employee_id:
                to_dt = fields.Datetime.from_string(rec.end_datetime).replace(tzinfo=UTC)
                to_dt = to_dt.astimezone(timezone(rec.employee_id.tz))
                rec.end_datetime_text = to_dt.strftime(strftime_pattern)
                
            else:
                rec.end_datetime_text = False
            if rec.start_datetime and rec.employee_id:
                from_dt = fields.Datetime.from_string(rec.start_datetime).replace(tzinfo=UTC)
                from_dt = from_dt.astimezone(timezone(rec.employee_id.tz))
                rec.start_datetime_text =  from_dt.strftime(strftime_pattern)
            else:
                rec.start_datetime_text = False
        
    @api.multi
    @api.depends('state')
    def button_privilege(self):
        employee_id = self.env['hr.employee'].search([('user_id','=',self._uid)],limit = 1)
        if employee_id:
            for rec in self:
                if employee_id.id == rec.employee_id.parent_id.id:
                    rec.do_first_approval = True
                if employee_id.id == rec.employee_id.department_id.manager_id.id:
                    rec.do_second_approval = True
        ad_mng = self.env.user.has_group('account.group_account_manager') or  self.env.user.has_group('hr_payroll.group_hr_payroll_manager')or  self.env.user.has_group('hr.group_hr_manager')

        if ad_mng:
            self.update({'do_done': True })
            
            
    @api.multi
    @api.depends('state')
    def _compute_is_employee(self):
        is_officer = self.env.user.has_group('hr.group_hr_user')
        self.update({'is_employee': not is_officer })
    
    
    @api.model
    def default_get(self, fields_list):
        res = super(hr_overtime, self).default_get(fields_list)
        employee_id = self.env['hr.employee'].search([('user_id','=',self._uid)],limit = 1)
        res['employee_id'] = employee_id and employee_id.id or False
        return res
        
    @api.multi
    @api.depends('state')
    def _compute_show_analytic_fields(self):
        show_analytic_fields = self.env.user.company_id.overtime_analytic == 'with_entries'
        for rec in self:
            rec.show_analytic_fields = show_analytic_fields
    
    @api.model
    @api.returns('self', lambda value:value.id)
    def create(self, vals):
        res = super(hr_overtime, self).create(vals)
        add_follower = self.env['mail.wizard.invite'].create({'res_model':self._name, 'res_id':res.id,
                                           'partner_ids':[(4, id) for id in self.env.user.company_id.users_to_notify_ot_ids.mapped('partner_id.id') + res.employee_id.mapped('parent_id.user_id.partner_id.id') + res.employee_id.mapped('department_id.manager_id.user_id.partner_id.id')]})
        add_follower.add_followers()
        return res
    @api.multi
    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError('You cannon delete confirmed record')
        return super(hr_overtime, self).unlink()
    

    @api.onchange('end_datetime', 'start_datetime','employee_id')
    @api.constrains('employee_id', 'end_datetime', 'start_datetime')
    def constrains_employee_id(self):
        payslip_obj = self.env['hr.payslip']
        if not (self.employee_id and self.start_datetime and self.end_datetime):
            return
        contract_ids = payslip_obj.get_contract(self.employee_id , self.start_datetime, self.end_datetime)
        if not contract_ids:
            raise UserError("Please make sure the employee has a running contract.")
   
    @api.constrains('end_datetime', 'start_datetime')
    def date_constrains(self):
        for rec in self:
            if rec.start_datetime and rec.end_datetime and rec.start_datetime > rec.end_datetime:
                raise UserError(_('The start date must be before the end date.'))
    def init_calendar(self):
        List_global = []
        List_working_time = []
        self_resource_calendar = self.env['resource.calendar'].search([])
        for rec_calander in self_resource_calendar:
            for i in range(len(rec_calander.global_leave_ids)):
                from_dt = rec_calander.global_leave_ids[i].date_from
                to_dt = rec_calander.global_leave_ids[i].date_to
                from_dt = from_dt.astimezone(timezone(self.employee_id.tz))
                to_dt = to_dt.astimezone(timezone(self.employee_id.tz))
                vals = {
                    'dayFrom' : from_dt,
                    'dayTo' : to_dt
                }
                List_global.append(vals)
        for rec_calander in self_resource_calendar:
            for i in range(len(rec_calander.attendance_ids)):
                vals = {
                    'name' : rec_calander.attendance_ids[i].name,
                    'dayOfWeek' : rec_calander.attendance_ids[i].dayofweek,
                    'hourFrom' : rec_calander.attendance_ids[i].hour_from,
                    'hourTo': rec_calander.attendance_ids[i].hour_to,
                    'dayPeriod': rec_calander.attendance_ids[i].day_period
                }
                List_working_time.append(vals)
            break
        
        hr_overtime.global_leave = List_global
        hr_overtime.working_time = List_working_time

    def isGlobalLeave(self,current):
        for d in range(len(hr_overtime.global_leave)):
            dayGlobalFrom = hr_overtime.global_leave[d].get('dayFrom')
            dayGlobalTo = hr_overtime.global_leave[d].get('dayTo')
            if dayGlobalFrom <= current and current <= dayGlobalTo:
                return True
        return False
    def splitByTime(self,hourFrom,hourTo):
        duration = []
        rangeStart = hourFrom
        isContinue = True
        while(isContinue):
            for i in range(len(hr_overtime.anchor_time)):
                if self.isGlobalLeave(rangeStart) == True:
                    dayType = 'global_leave'
                else:
                    dayType = 'normal_day'
                if hr_overtime.anchor_time[i].get('anchor') == 24:
                    anchorTime = rangeStart.replace(hour = 0, minute = 0 , second = 0) + timedelta(days = 1)
                else:
                    anchorTime = rangeStart.replace(hour = hr_overtime.anchor_time[i].get('anchor'), minute = 0 , second = 0)
                if anchorTime > rangeStart:
                    rangeEnd = anchorTime
                    if hourTo < anchorTime:
                        rangeEnd = hourTo
                        isContinue = False
                        
                    currentHourFrom = rangeStart.hour + rangeStart.minute/60

                    if rangeEnd.hour > 0:
                            currentHourTo = rangeEnd.hour + rangeEnd.minute/60
                    else:
                            currentHourTo = 24
                    currentHoursOvertime = currentHourTo - currentHourFrom
                    dictDayType = hr_overtime.bonus_by_daytype.get(dayType)
                    
                    currentBonus = dictDayType[str(rangeStart.weekday())] + hr_overtime.anchor_time[i].get('bonus')
                    current = {
                        'date' : rangeStart,
                        'dayOfWeek': rangeStart.weekday(),
                        'bonus': currentBonus,
                        'hourFrom': currentHourFrom,
                        'hourTo': currentHourTo,
                        'hoursWorking': 0,
                        'hoursOvertime': currentHoursOvertime,
                        'dayType': dayType
                    }
                    duration.append(current)

                    if isContinue == False: 
                        break

                    rangeStart = anchorTime
        return duration
    def calculateOvertime(self,overtimeFrom, overtimeTo):
        overtime = self.splitByTime(overtimeFrom, overtimeTo)
        for i in range(len(overtime)):
            current = overtime[i]
            if current.get('dayType') != 'global_leave':
                for d in range(len(hr_overtime.working_time)):
                    hoursWorking = hr_overtime.working_time[d]
                    print(hoursWorking)
                    if int(hoursWorking.get('dayOfWeek')) == current.get('dayOfWeek'):
                        #print("EEEEEEEEEEEE")
                        if hoursWorking.get('hourFrom') < current.get('hourTo') and hoursWorking.get('hourTo') > current.get('hourFrom'):
                            #print("DDDDDĐ")
                            if hoursWorking.get('hourFrom') < current.get('hourFrom'):
                                work_start = current.get('hourFrom')
                            else:
                                work_start = hoursWorking.get('hourFrom')
                            
                            if hoursWorking.get('hourTo') > current.get('hourTo'):
                                work_end = current.get('hourTo')
                            else:
                                work_end = hoursWorking.get('hourTo')
                            temp = current.get('hoursWorking')
                            temp+= work_end - work_start
                            overtime[i].update({'hoursWorking': temp})
                    temp = current.get('hourTo') - current.get('hourFrom') - overtime[i].get('hoursWorking')
                    overtime[i].update({'hoursOvertime': temp})
        return overtime
    def get_hour(self):
        for rec in self:
            rec.tang_ca_ngay_le = 0.0
            rec.tang_ca_ngay_le22 = 0.0
            rec.tang_ca_ngay_thuong = 0.0
            rec.tang_ca_ngay_thuong22 = 0.0
            rec.tang_ca_ngay_cuoi_tuan= 0.0
            rec.tang_ca_ngay_cuoi_tuan22 = 0.0
            #chagne UTC to employee timezone
            from_dt = fields.Datetime.from_string(rec.start_datetime).replace(tzinfo=UTC)
            to_dt = fields.Datetime.from_string(rec.end_datetime).replace(tzinfo=UTC)
            from_dt = from_dt.astimezone(timezone(rec.employee_id.tz))
            to_dt = to_dt.astimezone(timezone(rec.employee_id.tz))
            self.init_calendar()
            # print(self.isGlobalLeave(from_dt))
            # duration = self.splitByTime(from_dt,to_dt)
            #print(duration)
            overtime = self.calculateOvertime(from_dt,to_dt)
            print(overtime)
            for i in range(len(overtime)):
                dictOvertime = overtime[i]
                if dictOvertime.get('dayType') == 'global_leave':
                    if dictOvertime.get('hourFrom') >= 22:
                        rec.tang_ca_ngay_le22 += dictOvertime.get('hoursOvertime')
                    else:
                        rec.tang_ca_ngay_le += dictOvertime.get('hoursOvertime')
                elif dictOvertime.get('dayOfWeek') in [5,6]:
                    if dictOvertime.get('hourFrom') >= 22:
                        rec.tang_ca_ngay_cuoi_tuan22 +=dictOvertime.get('hoursOvertime')
                    else:
                        rec.tang_ca_ngay_cuoi_tuan +=dictOvertime.get('hoursOvertime')
                elif dictOvertime.get('dayOfWeek') not in [5,6]:
                    if dictOvertime.get('hourFrom') >= 22:
                        rec.tang_ca_ngay_thuong22 +=dictOvertime.get('hoursOvertime')
                    else:
                        rec.tang_ca_ngay_thuong +=dictOvertime.get('hoursOvertime')
        print("AAAAAAAAAAAAAAA")
    @api.one
    @api.depends('employee_id', 'start_datetime', 'end_datetime')
    def calculate_overtime(self):
        if not(self.start_datetime or self.end_datetime):
            self.cost = self.overtime = self.duration = 0.0
        payslip_obj = self.env['hr.payslip']
        contract_id = False   
        if self.start_datetime and self.end_datetime and self.employee_id:
            contract_ids = payslip_obj.get_contract(self.employee_id , self.start_datetime, self.end_datetime)
            if contract_ids:
                contract_id = self.env['hr.contract'].browse(contract_ids[0])
            from_dt = fields.Datetime.from_string(self.start_datetime).replace(tzinfo=UTC)
            to_dt = fields.Datetime.from_string(self.end_datetime).replace(tzinfo=UTC)
            from_dt = from_dt.astimezone(timezone(self.employee_id.tz))
            to_dt = to_dt.astimezone(timezone(self.employee_id.tz))
            # # just for overtime
            work_overtiem = 0.0
            off_overtiem = 0.0
            cost_by_hour = 0.0
            if contract_id:
                cost_by_hour = contract_id.wage / 30.4 / 8
                work_overtiem = contract_id.resource_calendar_id.overtime_work_days
                off_overtiem = contract_id.resource_calendar_id.overtime_off_days
            # #
            
            over_time = 0.0
            total_hours = 0.0 
            for r in self._calculate_durations(from_dt, to_dt, contract_id):
                total_hours += r[0]
                if r[1]:
                    over_time += r[0] * off_overtiem
                else:
                    over_time += r[0] * work_overtiem
            self.duration = total_hours
            self.overtime = over_time
            self.cost = over_time * cost_by_hour
    
    @api.model
    def _calculate_durations(self, from_dt , to_dt, contract_id):
        calendar = {}
        overtime_list = []
        for line in contract_id.resource_calendar_id.attendance_ids:
            dayofweek = int(line.dayofweek)
            if dayofweek not in calendar:
               calendar[dayofweek] = {'start':line.hour_from, 'end':line.hour_to}
            else:
                if line.hour_from < calendar[dayofweek]['start']:
                    calendar[dayofweek]['start'] = line.hour_from
                if line.hour_to > calendar[dayofweek]['end']:
                    calendar[dayofweek]['end'] = line.hour_to
        
        for from_dt , to_dt in period_datetime(from_dt, to_dt):
            float_time_from = from_dt.hour + from_dt.minute / 60
            float_time_to = to_dt.hour + to_dt.minute / 60
            dow = from_dt.weekday()
            if not self.is_off_day(from_dt  , contract_id, calendar):
                if float_time_from > calendar[dow]['end'] or  float_time_to < calendar[dow]['start']:
                    duration = (to_dt - from_dt).total_seconds() / 60 / 60
                    overtime_list.append([duration, False])
                else:
                    if float_time_from < calendar[dow]['start']:
                        from_dt1 = from_dt.replace(minute=int((calendar[dow]['start'] - int(calendar[dow]['start'])) * 100 * 0.6), hour=int(calendar[dow]['start']))
                        duration = (from_dt1 - from_dt).total_seconds() / 60 / 60
                        overtime_list.append([duration, False])
                    if float_time_to > calendar[dow]['end']:
                        to_dt1 = to_dt.replace(minute=int((calendar[dow]['end'] - int(calendar[dow]['end'])) * 100 * 0.6), hour=int(calendar[dow]['end']))
                        duration = (to_dt - to_dt1).total_seconds() / 60 / 60
                        overtime_list.append([duration, False])
                    
            else:
                duration = (to_dt - from_dt).total_seconds() / 60 / 60
                overtime_list.append([duration, True])
        return overtime_list
    
    @api.model
    def is_off_day(self, date_time  , contract, calendar):
        if 'hr.public_holiday' in self.env:
            public_holiday = self.env['hr.leave'].search([('date', '>=', str(date_time)[:10] + ' 00:00:00'),
                                                                   ('date_to', '<=', str(date_time)[:10] + ' 23:59:59'),
                                                                   ('holiday_status_id.is_public_holiday', '=', True),
                                                                   ('state', '=', 'validate'),
                                                                   ('employee_id', '=', contract.employee_id.id)])
            if public_holiday:
                return True
            
        if date_time.weekday() not in calendar:
            return True
        return False
        
    @api.multi
    def done_overtime(self):
        analytic_line_pool = self.env['account.analytic.line']
        timenow = time.strftime('%Y-%m-%d')
        tag = self.env.ref('hr_overtime_management.overtime_tag')
        general_account_id = False
        vals_1 = {'state':'done'}
        if self.show_analytic_fields:
            vals = {
                    'name': _('Overtime for ') + str(self.employee_id.name),
                    'account_id': self.analytic_account_id and self.analytic_account_id.id or False,
                    'tag_ids' : [(6, 0, [tag.id])],
                    'date': timenow,
                    'unit_amount': self.overtime,
                    'general_account_id': self.env.user.company_id.overtime_account_id.id,
                    'amount': self.cost * -1,
                    }
            res = analytic_line_pool.create(vals)
            vals_1['analytic_line_id'] = res.id
        self.write(vals_1)    
        return True
        
    @api.multi
    def confirm(self):
        self.write({'state':'confirmed'})  
        
    @api.multi
    def first_approve(self):
        self.write({'state':'first_approve'})    
        
    @api.multi
    def second_approve(self):
        self.write({'state':'second_approve'})

    @api.multi
    def draft(self): 
        self.write({'state':'draft'})
        
    @api.multi
    def cancel(self):
        self.analytic_line_id.unlink()
        self.write({'state':'cancel'})
    
    
     
class hr_payslip_inhe(models.Model): 
    _inherit = 'hr.payslip'
    
    
    @api.multi
    def refund_sheet(self):
        for payslip in self:
            overtime_ids = self.env['hr.overtime'].search([('state', '=', 'done'),
                                                                ('employee_id', '=', self.employee_id.id),
                                                                ('date', '>=', self.date_from),
                                                                ('date', '<=', self.date_to)])
            overtime_ids.write({'payslip_id':False})
        return super(hr_payslip_inhe, self).refund_sheet()
    
    @api.multi
    def action_payslip_done(self):
        res = super(hr_payslip_inhe, self).action_payslip_done()
        for payslip in self.filtered(lambda x: not x.credit_note):
            overtime_ids = self.env['hr.overtime'].search([('state', '=', 'done'),
                                                                ('employee_id', '=', payslip.employee_id.id),
                                                                ('date', '>=', payslip.date_from),
                                                                ('date', '<=', payslip.date_to)])
            
            overtime_ids.write({'payslip_id':payslip.id})
        
        return res
    
    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        res = super(hr_payslip_inhe, self).get_inputs(contracts, date_from, date_to)
        ot_obj = self.env['hr.overtime']
        if self.employee_id and date_from and date_to and contracts:
            contract =  contracts[0]
            
            if self.env.user.company_id.overtime_type == 'request':
                overtime_ids = self.env['hr.overtime'].search([('state', '=', 'done'),
                                                                ('employee_id', '=', self.employee_id.id),
                                                                ('date', '>=', fields.Date.to_string(date_from)),
                                                                ('date', '<=', fields.Date.to_string(date_to)),
                                                                ('payslip_id', '=', False)])
                if overtime_ids:
                    total_overtimes = 0.0
                    total_overtimes_holiday = 0.0
                    for rec in overtime_ids:
                        total_overtimes += rec.cost
                             
                    if total_overtimes:
                        vals = {'name': 'Overtime', 'code': 'OTN', 'amount': total_overtimes, 'contract_id': contract.id}
                        res += [vals]
            elif self.env.user.company_id.overtime_type == 'attendance':
                att_ids = self.env['hr.attendance'].search([('employee_id', '=', contract.employee_id.id),
                                                  ('check_in', '>=', fields.Date.to_string(date_from)),
                                                  ('check_in', '<', fields.Date.to_string(date_to) + ' 24:00:00'),
                                                  ('check_out', '!=', False)])
                overtime_list = []
                for att_id in att_ids:
                    check_in = fields.Datetime.from_string(att_id.check_in).replace(tzinfo=UTC)
                    check_in = check_in.astimezone(timezone(att_id.employee_id.tz))
                    check_out = fields.Datetime.from_string(att_id.check_out).replace(tzinfo=UTC)
                    check_out = check_out.astimezone(timezone(att_id.employee_id.tz))
                    overtime  = ot_obj._calculate_durations( check_in, check_out,contract)
                    if overtime:
                        overtime_list.extend(overtime)
                if overtime_list:
                    cost_by_hour = contract.wage / 30.4 / 8
                    work_overtiem = contract.resource_calendar_id.overtime_work_days
                    off_overtiem = contract.resource_calendar_id.overtime_off_days
                    toata_hours = 0.0
                    for i in overtime_list:
                        toata_hours += i[0] * (off_overtiem if i[1] else work_overtiem)
                    vals = {'name': 'Overtime %0.2f Hour(s)'%toata_hours, 'code': 'OTN', 'amount': toata_hours * cost_by_hour, 'contract_id': contract.id}
                    res += [vals]
                
        return res
